from __future__ import annotations

import base64
import io
import zipfile
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


def build_native_svg_pptx(svg_dir: Path, output_path: Path) -> Path:
    """Build a widescreen PPTX with each source page embedded as native SVG."""
    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        raise ValueError(f"SVG directory is empty: {svg_dir}")

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

    with zipfile.ZipFile(output_path) as archive:
        embedded_svgs = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/media/") and name.endswith(".svg")
        ]
    if len(embedded_svgs) < len(svg_files):
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Native SVG embedding check failed: expected {len(svg_files)} SVG media files, "
            f"found {len(embedded_svgs)}"
        )

    return output_path
