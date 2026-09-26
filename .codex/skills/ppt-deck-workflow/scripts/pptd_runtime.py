"""Small deterministic adapter for the pinned local PPTD editor/exporter."""
from __future__ import annotations

import functools
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import webbrowser
import zipfile
from xml.etree import ElementTree as ET

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "pptd"
WASM = ASSETS / "editor" / "neo-ppt" / "assets" / "pptd_wasm_bg-DPPWdROu.wasm"
ELEMENT_TYPES = {"text", "shape", "line", "image", "icon", "table", "chart"}


def project_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"invalid project path: {relative!r}")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or ":" in relative:
        raise ValueError(f"project path must be local and relative: {relative}")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"project path escapes root: {relative}")
    return result


def load_mapping(path: Path) -> dict:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return data


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate_project(root: Path, expected_pages: int | None = None) -> dict:
    root = root.resolve()
    manifests = list(root.glob("*.pptd"))
    if len(manifests) != 1:
        raise ValueError("PPTD project must contain exactly one .pptd manifest")
    manifest_path = project_path(root, manifests[0].name)
    manifest = load_mapping(manifest_path)
    if manifest.get("version") != "v2":
        raise ValueError("PPTD manifest must use version: v2")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages or not all(isinstance(p, str) for p in pages):
        raise ValueError("PPTD pages must be a non-empty list of relative paths")
    if len(set(pages)) != len(pages):
        raise ValueError("duplicate PPTD page paths")
    if expected_pages is not None and len(pages) != expected_pages:
        raise ValueError(f"PPTD page count {len(pages)} differs from approved {expected_pages}")
    size = manifest.get("size", [960, 540])
    if not isinstance(size, list) or len(size) != 2 or any(not finite_number(v) or v <= 0 for v in size):
        raise ValueError("PPTD size must contain two positive finite numbers")
    media = set()
    counts = {}
    warnings = []
    documents = [manifest]
    for rel in pages:
        page_path = project_path(root, rel)
        if page_path.suffix != ".page":
            raise ValueError(f"expected .page file: {rel}")
        page = load_mapping(page_path)
        documents.append(page)
        elements = page.get("elements")
        if not isinstance(elements, list) or not elements:
            raise ValueError(f"page elements must be a non-empty list: {rel}")
        ids = set()
        for element in elements:
            if not isinstance(element, dict):
                raise ValueError(f"invalid element in {rel}")
            element_id = element.get("elementId")
            kind = element.get("elementType")
            if not isinstance(element_id, str) or not element_id or element_id in ids:
                raise ValueError(f"missing/duplicate elementId in {rel}")
            ids.add(element_id)
            if not isinstance(kind, str) or kind not in ELEMENT_TYPES:
                raise ValueError(f"unsupported elementType in {rel}: {kind}")
            bounds = element.get("bounds")
            if not isinstance(bounds, list) or len(bounds) != 4 or any(not finite_number(v) for v in bounds):
                raise ValueError(f"invalid bounds in {rel}: {element_id}")
            x, y, w, h = bounds
            if w < 0 or h < 0:
                raise ValueError(f"negative element size in {rel}: {element_id}")
            if x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
                warnings.append(f"{rel}:{element_id} extends beyond page; inspect intentional cropping")
            if kind == "text":
                content = element.get("content")
                if not isinstance(content, dict) or not isinstance(content.get("text"), str):
                    raise ValueError(f"text content missing in {rel}: {element_id}")
            if kind == "image" and not isinstance(element.get("src"), str):
                raise ValueError(f"image src missing in {rel}: {element_id}")
            counts[kind] = counts.get(kind, 0) + 1
    for document in documents:
        for obj in walk(document):
            if "src" in obj:
                rel = obj["src"]
                path = project_path(root, rel)
                if not path.is_file():
                    raise ValueError(f"missing local media: {rel}")
                media.add(rel)
    return {"manifest": str(manifest_path), "pages": pages, "element_counts": counts,
            "media_count": len(media), "warnings": warnings, "visual_review": "not_performed"}


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def export_project(root: Path, output: Path) -> dict:
    report = validate_project(root)
    # Node adapter does not run the browser's icon/math/complex-chart preprocessing.
    for rel in report["pages"]:
        page = load_mapping(project_path(root, rel))
        for element in page["elements"]:
            if element["elementType"] == "icon" and not element.get("path"):
                raise ValueError("Named icons require browser export or an explicit shape path")
            if any(obj.get("type") in {"heatmap", "sankey", "treemap", "sunburst"}
                   for obj in walk(element) if isinstance(obj.get("type"), str)):
                raise ValueError("Complex charts require browser export (may become images)")
            text = (element.get("content") or {}).get("text", "")
            if isinstance(text, str) and ("data-latex" in text or "<math" in text):
                raise ValueError("Formula preprocessing requires browser export")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("PPTD export requires Node.js 18+ on PATH")
    version = subprocess.run([node, "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if int(version.lstrip("v").split(".")[0]) < 18:
        raise RuntimeError("PPTD export requires Node.js 18+")
    if not WASM.is_file():
        raise RuntimeError("Bundled PPTD WASM is missing; repair the Skill installation")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_suffix(".pending.pptx")
    try:
        result = subprocess.run(
            [node, str(ASSETS / "export-pptd.mjs"), report["manifest"], "-o", str(staged),
             "--wasm", str(WASM), "--no-sign"],
            env={**os.environ, "PPTD_PYTHON": sys.executable},
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode:
            raise RuntimeError(f"PPTD export failed:\n{result.stdout}\n{result.stderr}")
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("PPTX ZIP integrity check failed")
            names = archive.namelist()
            slides = [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            if len(slides) != len(report["pages"]):
                raise RuntimeError("PPTX page count differs from PPTD")
            texts = sum(len(ET.fromstring(archive.read(n)).findall(
                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}t")) for n in slides)
            if report["element_counts"].get("text") and not texts:
                raise RuntimeError("PPTX lost all editable text")
            fonts = sum(n.startswith("ppt/fonts/") and not n.endswith("/") for n in names)
        staged.replace(output)
    finally:
        staged.unlink(missing_ok=True)
    return {**report, "output": str(output), "exporter": "local-wasm",
            "text_runs": texts, "embedded_font_parts": fonts,
            "font_embedding": "not_supported_by_cli", "zip_integrity": "passed"}


class EditorHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.allowed_path():
            self.send_error(403)
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.allowed_path():
            self.send_error(403)
            return
        super().do_HEAD()

    def allowed_path(self):
        relative = unquote(urlsplit(self.path).path).lstrip("/")
        root = Path(self.directory).resolve()
        return ".." not in PurePosixPath(relative).parts and (root / relative).resolve().is_relative_to(root)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None

    def log_message(self, format, *args):
        pass


def create_editor_server(port: int = 0) -> ThreadingHTTPServer:
    editor = ASSETS / "editor"
    if not (editor / "index.html").is_file():
        raise RuntimeError("Bundled PPTD editor missing")
    handler = functools.partial(EditorHandler, directory=str(editor))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve_editor(project: Path, port: int = 0, open_browser: bool = False) -> None:
    with create_editor_server(port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"editor_url={url}", flush=True)
        print(f"project_dir={project.resolve()}", flush=True)
        print("editor_action=Open this PPTD folder in the editor; allow read/write to save edits", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
