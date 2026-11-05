"""Clean deliverables and recover embedded IMG originals without ad-hoc scripts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

CANONICAL = {'outline.json', 'contents.json', 'slide-plans.json'}
TEMPORARY = {
    '.workflow', 'render-jobs', 'img-prompts', 'img',
    'workflow-state.json', 'slide-status.json', 'slide-status-img.json',
    'slide-status-pptd.json', 'outline-preview.md', 'contents-preview.md',
    'slide-plans-preview.md', 'img-svg-chain.json', 'pptd-export.json',
}
PPTD_TEMPORARY = {'.qa-images', 'visual-review.md', 'reconstruction-review.md'}


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_digest(path: Path) -> str:
    value = read_json(path)
    if path.name == 'slide-plans.json' and isinstance(value, dict):
        value = {k: v for k, v in value.items() if k != '_delivery'}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError(f'cleanup path must be relative: {relative}')
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError(f'cleanup refuses links/junctions: {relative}')
    if path.resolve() == root or not path.resolve().is_relative_to(root):
        raise ValueError(f'cleanup path escapes run: {relative}')
    return path


def check_tree(root: Path):
    # Check every entry before deleting anything, including nested Windows junctions.
    for child in root.iterdir():
        safe_path(root, child.name)
        if child.is_dir():
            check_tree(child)


def pptx_page_count(path: Path) -> int:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise ValueError(f'corrupt PPTX: {path.name}')
            archive.read('[Content_Types].xml')
            presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
            count = len(presentation.findall('{*}sldIdLst/{*}sldId'))
            slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
            if not count or count != len(slides):
                raise ValueError(f'incomplete PPTX: {path.name}')
            return count
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError(f'invalid PPTX: {path.name}') from exc


def img_blobs(pptx: Path) -> list[tuple[bytes, str]]:
    from pptx import Presentation
    from PIL import Image
    result = []
    deck = Presentation(pptx)
    for slide in deck.slides:
        if len(slide.shapes) != 1 or slide.shapes[0].shape_type != 13:
            raise ValueError('IMG recovery requires one full-page picture per slide')
        shape = slide.shapes[0]
        if shape.left != 0 or shape.top != 0 or shape.width != deck.slide_width or shape.height != deck.slide_height:
            raise ValueError('IMG recovery requires a full-page picture')
        blob = shape.image.blob
        with Image.open(io.BytesIO(blob)) as image:
            image.verify()
        result.append((blob, shape.image.ext))
    return result


def _pptd_files(root: Path, count: int) -> set[str]:
    from pptd_runtime import load_mapping, project_path, validate_project, walk
    project = root / 'pptd'
    report = validate_project(project, expected_pages=count)
    manifest = Path(report['manifest'])
    keep = {manifest.relative_to(root).as_posix()}
    for path in [manifest, *(project / p for p in report['pages'])]:
        keep.add(path.relative_to(root).as_posix())
        for obj in walk(load_mapping(path)):
            if 'src' in obj:
                keep.add(project_path(project, obj['src']).relative_to(root).as_posix())
    if (project / 'media-sources.json').is_file():
        keep.add('pptd/media-sources.json')
    return keep


def inspect_delivery(root: Path) -> list[str]:
    """Read-only integrity report for a cleaned run; never infer missing approval."""
    root = root.resolve()
    metadata = (read_json(root / 'slide-plans.json', {}) or {}).get('_delivery') or {}
    issues = []
    for key, name in [('outline', 'outline.json'), ('contents', 'contents.json'), ('slide_plans', 'slide-plans.json')]:
        path = root / name
        if not path.is_file() or metadata.get('artifact_sha256', {}).get(key) != artifact_digest(path):
            issues.append(f'{name} missing or changed')
    exports = metadata.get('exports') or []
    if not exports:
        issues.append('no recorded exports')
    for item in exports + (metadata.get('project_files') or []):
        try:
            path = safe_path(root, item['path'])
            if not path.is_file() or item.get('sha256') != file_digest(path):
                issues.append(f"{item['path']} missing or changed")
        except (ValueError, KeyError, TypeError):
            issues.append('invalid delivery path')
    return issues


def finalize_delivery(run_dir: Path, *, apply: bool = False, discard=(), retain=()) -> dict:
    if run_dir.is_symlink() or (hasattr(run_dir, 'is_junction') and run_dir.is_junction()):
        raise ValueError('run directory must not be a link/junction')
    root = run_dir.resolve(strict=True)
    check_tree(root)
    for name in CANONICAL:
        if not (root / name).is_file():
            raise ValueError(f'missing canonical artifact: {name}')
    plans = read_json(root / 'slide-plans.json')
    count = len(plans.get('slides') or [])
    if not count:
        raise ValueError('slide-plans.json has no slides')
    old = plans.get('_delivery') or {}
    state = read_json(root / 'workflow-state.json', {})
    brief = read_json(root / '.workflow/task-brief.json', old.get('task_brief', {}))
    if brief.get('pending_work'):
        raise ValueError('finish task brief pending_work before finalization')
    for renderer, entry in state.get('renderers', {}).items():
        if not entry.get('artifacts', {}).get('pptx'):
            continue
        exported = entry['artifacts']['pptx']
        path = Path(exported['path'])
        if (not path.is_file() or exported.get('sha256') != file_digest(path) or
                (renderer == state.get('renderer') and entry.get('export_plan_sha256') != file_digest(root / 'slide-plans.json'))):
            raise ValueError(f'{renderer} export is stale or lacks provenance; re-export before cleanup')
        if renderer == 'pptd':
            from pptd_visual import build_payload
            if entry.get('export_project_sha256') != build_payload(root / 'pptd')[2]:
                raise ValueError('PPTD changed after export; re-export before cleanup')
    exports = sorted(root.glob('*.pptx'))
    if not exports:
        raise ValueError('no PPTX export; preserve working files')
    for path in exports:
        if pptx_page_count(path) != count:
            raise ValueError(f'PPTX page count differs from slide plans: {path.name}')
    keep = CANONICAL | {p.name for p in exports}
    if (root / 'pptd').exists():
        keep |= _pptd_files(root, count)
    for rel in retain:
        path = safe_path(root, rel)
        if not path.exists():
            raise ValueError(f'requested deliverable is missing: {rel}')
        keep.update(p.relative_to(root).as_posix() for p in ([path] if path.is_file() else path.rglob('*')) if p.is_file())
    discard_paths = []
    for rel in discard:
        target = safe_path(root, rel)
        normalized = target.relative_to(root).as_posix()
        if any(p == normalized or p.startswith(normalized + '/') for p in keep):
            raise ValueError(f'cannot discard a deliverable or dependency: {rel}')
        discard_paths.append(normalized)
    candidates, unknown = [], []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in keep:
            continue
        parts = Path(rel).parts
        temporary = parts[0] in TEMPORARY or (
            len(parts) > 1 and parts[0] == 'pptd' and parts[1] in PPTD_TEMPORARY)
        if temporary or any(rel == p or rel.startswith(p + '/') for p in discard_paths):
            candidates.append(rel)
        else:
            unknown.append(rel)
    # Raw IMG pixels are recoverable from the retained image PPTX, not discarded blindly.
    images = sorted(p for p in (root / 'img').glob('*') if p.is_file())
    if images and any(p.relative_to(root).as_posix() in candidates for p in images):
        expected = [file_digest(p) for p in images]
        recoverable = False
        for path in exports:
            try:
                recovered = [hashlib.sha256(blob).hexdigest() for blob, _ in img_blobs(path)]
                if expected == recovered:
                    recoverable = True
                    break
            except (ValueError, KeyError):
                continue
        if not recoverable:
            raise ValueError('IMG originals have no byte-identical PPTX backup; preserve them')
    result = {'applied': False, 'keep': sorted(keep), 'remove': sorted(candidates),
              'unclassified': sorted(unknown), 'explicit_discard': discard_paths}
    if not apply:
        return result
    if unknown:
        raise ValueError('unclassified files: ' + ', '.join(sorted(unknown)))
    metadata = {
        'version': 1, 'completed_at': old.get('completed_at') or datetime.now(timezone.utc).isoformat(),
        'topic': state.get('topic', old.get('topic', root.name)), 'audience': state.get('audience', old.get('audience')),
        'task_brief': brief, 'renderer': state.get('renderer', old.get('renderer')),
        'renderer_sources': {k: v.get('source', 'plans') for k, v in state.get('renderers', {}).items()}
                            or old.get('renderer_sources', {}),
        'exports': [{'path': p.name, 'sha256': file_digest(p)} for p in exports],
        'project_files': [{'path': rel, 'sha256': file_digest(root / rel)} for rel in sorted(keep)
                          if rel not in CANONICAL and rel not in {p.name for p in exports}],
        'artifact_sha256': {key: artifact_digest(root / name) for key, name in (
            ('outline', 'outline.json'), ('contents', 'contents.json'), ('slide_plans', 'slide-plans.json'))},
        'verification': 'PPTX integrity, page count and local dependencies; visual review remains agent responsibility',
    }
    plans['_delivery'] = metadata
    staged = root / '.workflow/delivery-plans.pending.json'
    staged.parent.mkdir(exist_ok=True)
    staged.write_text(json.dumps(plans, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    staged.replace(root / 'slide-plans.json')
    for rel in candidates:
        safe_path(root, rel).unlink()
    for path in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(path.iterdir()):
            path.rmdir()
    result['applied'] = True
    return result


def restore_img_sources(run_dir: Path, pptx: Path) -> list[Path]:
    """Restore original image bytes for a requested derivative after final cleanup."""
    from filename_utils import slide_filename
    root = run_dir.resolve(strict=True)
    check_tree(root)
    plans = read_json(root / 'slide-plans.json')
    recorded = (plans.get('_delivery') or {}).get('exports') or []
    state = read_json(root / 'workflow-state.json', {})
    original = state.get('renderers', {}).get('img', {}).get('artifacts', {}).get('pptx')
    if original:
        recorded = [*recorded, original]
    if not any(item.get('sha256') == file_digest(pptx) for item in recorded):
        raise ValueError('IMG recovery source does not match a recorded export')
    blobs = img_blobs(pptx)
    slides = plans['slides']
    if len(blobs) != len(slides):
        raise ValueError('IMG PPTX page count differs from current slide plans')
    targets = [root / 'img' / slide_filename(i, s['title'], f'.{ext}')
               for i, (s, (_, ext)) in enumerate(zip(slides, blobs), 1)]
    for target, (blob, _) in zip(targets, blobs):
        if target.exists() and target.read_bytes() != blob:
            raise ValueError(f'existing IMG differs; refusing overwrite: {target.name}')
    (root / 'img').mkdir(exist_ok=True)
    for target, (blob, _) in zip(targets, blobs):
        target.write_bytes(blob)
    return targets
