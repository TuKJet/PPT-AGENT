"""Export local neo-ppt page images and a contact sheet for visual review."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import mimetypes
from pathlib import Path
import re
import shutil
import tempfile
import threading
import zipfile

from PIL import Image, ImageDraw, ImageFont

from pptd_runtime import create_editor_server, load_mapping, project_path, validate_project, walk
from playwright_runtime import launch_global_chromium, sync_playwright


def build_payload(root: Path) -> tuple[dict, dict, str]:
    report = validate_project(root)
    manifest_path = Path(report["manifest"])
    manifest_text = manifest_path.read_text(encoding="utf-8")
    pages = [{"path": rel, "content": project_path(root, rel).read_text(encoding="utf-8")}
             for rel in report["pages"]]
    documents = [load_mapping(manifest_path)] + [load_mapping(project_path(root, rel)) for rel in report["pages"]]
    media = sorted({obj["src"] for doc in documents for obj in walk(doc) if "src" in obj})
    image_map = {}
    digest = hashlib.sha256(manifest_text.encode())
    for page in pages:
        digest.update(json.dumps(page, sort_keys=True).encode())
    for rel in media:
        data = project_path(root, rel).read_bytes()
        digest.update(rel.encode())
        digest.update(data)
        mime = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        image_map[rel] = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    payload = {"id": "local-visual-review", "title": documents[0].get("title", root.name),
               "manifestPath": manifest_path.name, "manifestContent": manifest_text,
               "pages": pages, "imageMap": image_map}
    return payload, report, digest.hexdigest()


def unpack_pages(archive_path: Path, output: Path, expected: int) -> list[Path]:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [item for item in archive.infolist() if not item.is_dir()
                   and Path(item.filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        def number(item):
            match = re.match(r"(\d+)", Path(item.filename).stem)
            if not match:
                raise ValueError(f"Page image lacks numeric order: {item.filename}")
            return int(match.group(1))
        entries.sort(key=number)
        numbers = [number(item) for item in entries]
        if len(entries) != expected or numbers not in [list(range(expected)), list(range(1, expected + 1))]:
            raise ValueError(f"Image export page order/count mismatch: {numbers}; expected {expected}")
        output.mkdir(parents=True)
        paths = []
        for index, item in enumerate(entries, 1):
            # Decode and re-encode rather than extracting archive paths.
            with Image.open(io.BytesIO(archive.read(item))) as image:
                image.load()
                target = output / f"{index:03d}.png"
                image.convert("RGB").save(target)
            paths.append(target)
        return paths


def stitch_overview(images: list[Path], output: Path) -> None:
    columns, width, gap, label = min(3, len(images)), 640, 12, 32
    thumbs = []
    for path in images:
        with Image.open(path) as image:
            thumbs.append(image.convert("RGB").resize(
                (width, max(1, round(width * image.height / image.width))), Image.Resampling.LANCZOS))
    cell = max(image.height for image in thumbs) + label
    canvas = Image.new("RGB", (columns * width + (columns + 1) * gap,
                               math.ceil(len(images) / columns) * (cell + gap) + gap), "#e5e7eb")
    draw, font = ImageDraw.Draw(canvas), ImageFont.load_default(size=18)
    for index, thumb in enumerate(thumbs):
        x, y = gap + (index % columns) * (width + gap), gap + (index // columns) * (cell + gap)
        draw.rectangle((x, y, x + width, y + label - 4), fill="#111827")
        draw.text((x + 8, y + 5), f"P{index + 1}", fill="white", font=font)
        canvas.paste(thumb, (x, y + label))
    canvas.save(output, "JPEG", quality=90)


def export_images(root: Path, *, force: bool = False) -> dict:
    root = root.resolve()
    output = root / ".qa-images"
    if output.is_symlink():
        raise ValueError("QA output must not be a symlink")
    if output.exists() and not force:
        raise ValueError("QA images already exist; use --force after edits")
    payload, report, fingerprint = build_payload(root)
    # Publish only a complete export; failed browser runs keep previous QA intact.
    with tempfile.TemporaryDirectory(prefix="pptd-qa-", dir=root) as temp:
        stage = Path(temp)
        with create_editor_server() as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as playwright:
                    browser = launch_global_chromium(playwright, headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
                        def route_request(route):
                            if route.request.url == origin + "/payload.json":
                                route.fulfill(json=payload)
                            elif route.request.url.startswith(origin + "/"):
                                route.continue_()
                            else:
                                route.abort()
                        page.route("**/*", route_request)
                        page.goto(origin + "/?ndExport=1")
                        page.wait_for_function("document.documentElement.dataset.deckStatus === 'ready'", timeout=120000)
                        page.get_by_role("button", name="导出", exact=True).click()
                        page.locator(".radio-group-item").filter(has_text=re.compile("^图片$")).click()
                        page.locator(".radio-group-item.active").filter(has_text=re.compile("^图片$")).wait_for()
                        with page.expect_download(timeout=240000) as download:
                            page.get_by_role("button", name="下载", exact=True).click()
                        download.value.save_as(stage / "browser-raw.zip")
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
        if build_payload(root)[2] != fingerprint:
            raise ValueError("PPTD changed during image export; save the project and retry")
        images = unpack_pages(stage / "browser-raw.zip", stage / "pages", len(report["pages"]))
        stitch_overview(images, stage / "overview.jpg")
        summary = {"source_sha256": fingerprint, "exporter": "browser-local-editor",
                   "visual_review": "pending", "remote_assets": "blocked; local fonts used",
                   "overview": str(output / "overview.jpg"), "page_count": len(images),
                   "images": [{"index": index, "page": rel, "image": f"pages/{image.name}"}
                              for index, (rel, image) in enumerate(zip(report["pages"], images), 1)]}
        (stage / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        stage.rename(output)
    return summary
