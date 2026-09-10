from __future__ import annotations

import base64
import hashlib
import io
import posixpath
import re
import zipfile
from collections.abc import Sequence
from xml.etree import ElementTree
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from playwright_runtime import launch_global_chromium, sync_playwright


SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)
VIEWPORT = {"width": 1280, "height": 720}


def svg_path_to_html(svg_path: Path) -> str:
    """Wrap one SVG page in a minimal document for deterministic rendering."""
    svg_content = svg_path.read_text(encoding="utf-8")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;width:1280px;height:720px;overflow:hidden;}"
        "svg{display:block;width:1280px;height:720px;}</style></head>"
        f"<body>{svg_content}</body></html>"
    )


def svg_to_png_bytes(svg_path: Path) -> bytes:
    """Render one SVG page to a 1280x720 PNG without changing the source."""
    html = svg_path_to_html(svg_path)
    with sync_playwright() as playwright:
        browser = launch_global_chromium(playwright)
        try:
            page = browser.new_page(viewport=VIEWPORT)
            page.set_content(html, wait_until="networkidle")
            page.evaluate("() => document.fonts && document.fonts.ready")
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            return page.screenshot(
                type="png",
                clip={"x": 0, "y": 0, **VIEWPORT},
            )
        finally:
            browser.close()


def build_pptx(svg_dir: Path, output_path: Path) -> Path:
    """Build a widescreen image PPTX from Codex-authored SVG pages."""
    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        raise ValueError(f"SVG directory is empty: {svg_dir}")

    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H
    blank_layout = presentation.slide_layouts[6]

    for svg_path in svg_files:
        png_bytes = svg_to_png_bytes(svg_path)
        slide = presentation.slides.add_slide(blank_layout)
        slide.shapes.add_picture(
            io.BytesIO(png_bytes),
            left=0,
            top=0,
            width=SLIDE_W,
            height=SLIDE_H,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(output_path))
    return output_path


def _svg_paths(svg_dir: Path, svg_paths: Sequence[Path] | None) -> list[Path]:
    if svg_paths is None:
        paths = sorted(svg_dir.glob("*.svg"))
    else:
        paths = [Path(path) for path in svg_paths]
    if not paths:
        raise ValueError(f"SVG directory is empty: {svg_dir}")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"SVG source is missing: {missing[0]}")
    return paths


def _style_declarations(value: str) -> dict[str, str]:
    """Parse the simple declaration form emitted by the browser exporter."""
    declarations: dict[str, str] = {}
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        name, item = declaration.split(":", 1)
        name = " ".join(name.lower().split())
        item = " ".join(item.lower().split())
        if name and item:
            declarations[name] = item
    return declarations


def _style_value_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    # Chromium serializes hex colors as rgb(...), while preserving the same style.
    if expected.startswith("#") and len(expected) in {4, 7}:
        digits = expected[1:]
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        rgb = tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))
        return actual.replace(" ", "") in {
            f"rgb({rgb[0]},{rgb[1]},{rgb[2]})",
            f"rgba({rgb[0]},{rgb[1]},{rgb[2]},1)",
        }
    return False


def _svg_signature(svg_text: str, reference_text: str | None = None) -> str:
    """Hash SVG structure, allowing only exporter-added root sizing and style declarations."""
    root = ElementTree.fromstring(svg_text)
    reference_root = ElementTree.fromstring(reference_text) if reference_text is not None else root

    def canonical(node: ElementTree.Element, reference: ElementTree.Element, *, is_root: bool) -> tuple:
        reference_attributes = {
            key.rsplit("}", 1)[-1]
            for key in reference.attrib
            if key.rsplit("}", 1)[-1] != "style"
            and not (is_root and key.rsplit("}", 1)[-1] in {"width", "height"})
        }
        attrs = tuple(
            sorted(
                (key.rsplit("}", 1)[-1], value)
                for key, value in node.attrib.items()
                if key.rsplit("}", 1)[-1] in reference_attributes
            )
        )
        expected_style = _style_declarations(reference.attrib.get("style", ""))
        actual_style = _style_declarations(node.attrib.get("style", ""))
        style = tuple(
            sorted(
                (name, value)
                for name, value in expected_style.items()
                if name in actual_style and _style_value_matches(value, actual_style[name])
            )
        )
        # A missing source declaration must change the signature as well.
        if len(style) != len(expected_style):
            style = ("__missing_source_style__",)
        if len(node) != len(reference):
            children = ("__child_count_mismatch__", len(node), len(reference))
        else:
            children = tuple(
                canonical(child, reference_child, is_root=False)
                for child, reference_child in zip(node, reference)
            )
        return (
            node.tag.rsplit("}", 1)[-1],
            attrs,
            style,
            node.text or "",
            node.tail or "",
            children,
        )

    return hashlib.sha256(repr(canonical(root, reference_root, is_root=True)).encode("utf-8")).hexdigest()


def _validate_native_svg_package(output_path: Path, svg_texts: Sequence[str]) -> None:
    """Verify slide-to-SVG relationships and preserve the submitted SVG order."""
    rel_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())
        slide_numbers = sorted(
            int(match.group(1))
            for name in names
            if (match := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name))
        )
        expected_numbers = list(range(1, len(svg_texts) + 1))
        if slide_numbers != expected_numbers:
            raise RuntimeError(
                f"Native SVG slide count/order check failed: expected {expected_numbers}, found {slide_numbers}"
            )

        expected_signatures = [_svg_signature(svg_text) for svg_text in svg_texts]

        referenced_svg_names: list[str] = []
        for slide_number, expected_signature in zip(slide_numbers, expected_signatures):
            slide_name = f"ppt/slides/slide{slide_number}.xml"
            slide_root = ElementTree.fromstring(archive.read(slide_name))
            svg_blips = [
                node
                for node in slide_root.iter()
                if node.tag.rsplit("}", 1)[-1] == "svgBlip"
            ]
            if len(svg_blips) != 1:
                raise RuntimeError(
                    f"Native SVG relationship check failed for slide {slide_number}: "
                    f"expected one svgBlip, found {len(svg_blips)}"
                )
            relationship_id = svg_blips[0].get(f"{rel_namespace}embed")
            rels_name = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
            if not relationship_id or rels_name not in names:
                raise RuntimeError(f"Native SVG relationship check failed for slide {slide_number}")
            rels_root = ElementTree.fromstring(archive.read(rels_name))
            target = next(
                (
                    relationship.get("Target")
                    for relationship in rels_root
                    if relationship.get("Id") == relationship_id
                ),
                None,
            )
            if not target:
                raise RuntimeError(
                    f"Native SVG relationship check failed for slide {slide_number}: "
                    f"missing target for {relationship_id}"
                )
            media_name = posixpath.normpath(
                posixpath.join(posixpath.dirname(slide_name), target)
            ).lstrip("/")
            if not media_name.startswith("ppt/media/") or not media_name.endswith(".svg") or media_name not in names:
                raise RuntimeError(
                    f"Native SVG relationship check failed for slide {slide_number}: invalid target {target}"
                )
            referenced_svg_names.append(media_name)
            actual_signature = _svg_signature(
                archive.read(media_name).decode("utf-8"),
                reference_text=svg_texts[slide_number - 1],
            )
            if actual_signature != expected_signature:
                raise RuntimeError(
                    f"Native SVG order/content check failed for slide {slide_number}: "
                    "embedded SVG does not match the submitted page"
                )

        archive_svg_names = sorted(
            name for name in names if name.startswith("ppt/media/") and name.endswith(".svg")
        )
        if len(archive_svg_names) != len(svg_texts) or set(referenced_svg_names) != set(archive_svg_names):
            raise RuntimeError(
                f"Native SVG media check failed: expected {len(svg_texts)} referenced SVG media files, "
                f"found {len(archive_svg_names)}"
            )


def build_native_svg_pptx(
    svg_dir: Path,
    output_path: Path,
    *,
    svg_paths: Sequence[Path] | None = None,
) -> Path:
    """Build a widescreen PPTX with each source page embedded as native SVG."""
    svg_files = _svg_paths(svg_dir, svg_paths)

    bundle_path = (
        Path(__file__).resolve().parent
        / "vendor_presentation_core"
        / "export"
        / "dom-to-pptx.bundle.js"
    )
    if not bundle_path.exists():
        raise FileNotFoundError(f"Native SVG PPT exporter bundle is missing: {bundle_path}")

    payload = {
        "fileName": output_path.name,
        "svgs": [path.read_text(encoding="utf-8") for path in svg_files],
    }
    with sync_playwright() as playwright:
        browser = launch_global_chromium(playwright)
        try:
            page = browser.new_page(viewport=VIEWPORT)
            page.set_content(
                "<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body style='margin:0'><main id='host'></main></body></html>"
            )
            page.add_script_tag(path=str(bundle_path))
            encoded = page.evaluate(
                """
                async (payload) => {
                  const host = document.getElementById('host');
                  const slides = payload.svgs.map((svgText) => {
                    const root = document.createElement('div');
                    root.style.cssText = [
                      'width:1280px',
                      'height:720px',
                      'position:relative',
                      'overflow:hidden',
                      'margin:0',
                      'padding:0',
                      'background:transparent'
                    ].join(';');
                    root.innerHTML = svgText;
                    const svg = root.querySelector('svg');
                    if (!svg) throw new Error('SVG source has no <svg> root');
                    svg.setAttribute('width', '1280');
                    svg.setAttribute('height', '720');
                    svg.style.cssText = 'display:block;width:1280px;height:720px';
                    host.appendChild(root);
                    return root;
                  });

                  const blob = await window.domToPptx.exportToPptx(slides, {
                    fileName: payload.fileName,
                    skipDownload: true,
                    svgAsVector: true,
                  });
                  const bytes = new Uint8Array(await blob.arrayBuffer());
                  let binary = '';
                  const chunkSize = 0x8000;
                  for (let i = 0; i < bytes.length; i += chunkSize) {
                    binary += String.fromCharCode.apply(
                      null,
                      bytes.subarray(i, i + chunkSize)
                    );
                  }
                  return btoa(binary);
                }
                """,
                payload,
            )
        finally:
            browser.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(encoded))

    try:
        _validate_native_svg_package(
            output_path,
            [path.read_text(encoding="utf-8") for path in svg_files],
        )
    except (ElementTree.ParseError, UnicodeDecodeError, KeyError, RuntimeError) as exc:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Native SVG embedding check failed: {exc}") from exc

    return output_path
