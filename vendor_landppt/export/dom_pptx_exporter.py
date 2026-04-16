from __future__ import annotations

import base64
import json
import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from html_pipeline.html_builder import render_html_screenshot, write_slide_status


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _HtmlTextSignalParser(HTMLParser):
    _IGNORED_TAGS = {"script", "style", "title", "head", "meta", "link", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._tag_stack: list[str] = []
        self.segments: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self._tag_stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == tag:
                del self._tag_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if any(tag in self._IGNORED_TAGS for tag in self._tag_stack):
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", text):
            return
        self.segments.append(text[:80])


def _estimate_html_text_signal(html: str) -> dict[str, Any]:
    parser = _HtmlTextSignalParser()
    parser.feed(html)
    parser.close()
    return {
        "text_node_count": len(parser.segments),
        "samples": parser.segments[:5],
    }


def _iter_shapes(shapes) -> Any:
    for shape in shapes:
        yield shape
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)


def _shape_text(shape) -> str:
    raw_text = getattr(shape, "text", "") or ""
    return re.sub(r"\s+", " ", raw_text).strip()


def _audit_exported_pptx(ppt_path: Path, slides: list[dict[str, Any]]) -> dict[str, Any]:
    deck = Presentation(str(ppt_path))
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    if len(deck.slides) != len(slides):
        failures.append(
            f"slide count mismatch: pptx={len(deck.slides)} html={len(slides)}"
        )

    for idx, slide_payload in enumerate(slides, start=1):
        ppt_slide = deck.slides[idx - 1] if idx - 1 < len(deck.slides) else None
        text_signal = _estimate_html_text_signal(slide_payload["html"])
        html_text_nodes = text_signal["text_node_count"]
        shape_count = 0
        text_shape_count = 0
        picture_shape_count = 0
        reasons: list[str] = []

        if ppt_slide is None:
            reasons.append("missing slide in exported pptx")
            status = "fail"
        else:
            all_shapes = list(_iter_shapes(ppt_slide.shapes))
            shape_count = len(all_shapes)
            for shape in all_shapes:
                if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:
                    picture_shape_count += 1
                if getattr(shape, "has_text_frame", False) and _shape_text(shape):
                    text_shape_count += 1

            min_text_shapes = 0
            min_total_shapes = 0
            if html_text_nodes >= 10:
                min_text_shapes = max(3, math.ceil(html_text_nodes * 0.12))
            elif html_text_nodes >= 4:
                min_text_shapes = 1
            if html_text_nodes >= 12:
                min_total_shapes = max(4, math.ceil(html_text_nodes * 0.18))
            elif html_text_nodes >= 4:
                min_total_shapes = 2

            screenshot_like = (
                html_text_nodes >= 3
                and shape_count <= 2
                and picture_shape_count >= 1
                and text_shape_count <= 1
            )
            if screenshot_like:
                reasons.append("pptx structure looks rasterized")
            if min_text_shapes and text_shape_count < min_text_shapes:
                reasons.append(
                    f"text shapes too low ({text_shape_count} < {min_text_shapes})"
                )
            if min_total_shapes and shape_count < min_total_shapes:
                reasons.append(
                    f"shape count too low ({shape_count} < {min_total_shapes})"
                )

            if screenshot_like or (len(reasons) >= 2 and html_text_nodes >= 10):
                status = "fail"
            elif reasons:
                status = "warn"
            else:
                status = "pass"

        result = {
            "index": idx,
            "title": slide_payload.get("title", f"slide-{idx:02d}"),
            "status": status,
            "shape_count": shape_count,
            "text_shape_count": text_shape_count,
            "picture_shape_count": picture_shape_count,
            "html_text_node_count": html_text_nodes,
            "html_text_samples": text_signal["samples"],
            "reasons": reasons,
        }
        results.append(result)
        if status == "fail":
            failures.append(
                f"slide {idx:02d} {result['title']}: " + "; ".join(reasons or ["audit failed"])
            )

    summary = {
        "pass": sum(1 for item in results if item["status"] == "pass"),
        "warn": sum(1 for item in results if item["status"] == "warn"),
        "fail": sum(1 for item in results if item["status"] == "fail"),
    }
    return {"slides": results, "failures": failures, "summary": summary}


def _write_dom_review(out_dir: Path, slide_result: dict[str, Any], html_path: Path) -> Path:
    review_path = out_dir / f"review-{slide_result['index']:02d}.md"
    status_label = {
        "pass": "PASS",
        "warn": "WARN",
        "fail": "FAIL",
    }[slide_result["status"]]
    lines = [
        f"# {html_path.name}",
        "",
        f"RESULT: {status_label}",
        "",
        "## Reasons",
    ]
    lines.extend([f"- {item}" for item in slide_result["reasons"]] or ["- DOM export passed pptx structure audit"])
    lines.extend(
        [
            "",
            "## Metrics",
            f"- shape_count: {slide_result['shape_count']}",
            f"- text_shape_count: {slide_result['text_shape_count']}",
            f"- picture_shape_count: {slide_result['picture_shape_count']}",
            f"- html_text_node_count: {slide_result['html_text_node_count']}",
            "",
            "## HTML Text Samples",
        ]
    )
    lines.extend([f"- {item}" for item in slide_result["html_text_samples"]] or ["- no sampled text nodes"])
    review_path.write_text("\n".join(lines), encoding="utf-8")
    return review_path


class DomPptxExporter:
    """Run LandPPT's browser-side DOM exporter inside Playwright."""

    def __init__(self, bundle_path: Path | None = None):
        self.bundle_path = bundle_path or (Path(__file__).resolve().parent / "dom-to-pptx.bundle.js")

    def export_slides(self, slides: list[dict[str, Any]], output_path: Path) -> Path:
        if not slides:
            raise ValueError("No slides provided for DOM export")

        shell_html = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>dom export</title></head><body></body></html>"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.set_content(shell_html, wait_until="domcontentloaded")
            page.add_script_tag(path=str(self.bundle_path))
            payload = {"slides": slides, "fileName": output_path.name}
            b64 = page.evaluate(
                """
                async (payload) => {
                  const host = document.createElement('div');
                  host.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0;pointer-events:none;';
                  document.body.appendChild(host);

                  function stabilizeLayoutForPpt(doc) {
                    const win = doc.defaultView;
                    if (!win) return;

                    const clampPx = (value, fallback = 0) => {
                      const parsed = Number.parseFloat(String(value ?? ''));
                      return Number.isFinite(parsed) ? parsed : fallback;
                    };

                    const stabilizeHeader = (header) => {
                      const headerStyle = win.getComputedStyle(header);
                      if (headerStyle.display !== 'flex') return;

                      const children = Array.from(header.children).filter(
                        (node) => node instanceof win.HTMLElement
                      );
                      if (children.length < 2) return;

                      const lead = children[0];
                      const tail = children[children.length - 1];
                      const headerRect = header.getBoundingClientRect();
                      const tailRect = tail.getBoundingClientRect();
                      if (!headerRect.width) return;

                      // Flex headers with `space-between` often keep the text column at max-content width.
                      // That is stable in Chromium, but PowerPoint may reflow with different font metrics.
                      const reserve = Math.max(110, tailRect.width + 36);
                      const available = Math.max(360, Math.floor(headerRect.width - reserve));

                      lead.style.flex = `0 0 ${available}px`;
                      lead.style.width = `${available}px`;
                      lead.style.maxWidth = `${available}px`;
                      lead.style.minWidth = '0';
                      if (!lead.style.paddingRight) {
                        lead.style.paddingRight = '24px';
                      }

                      tail.style.flex = '0 0 auto';
                      tail.style.marginLeft = '24px';
                      tail.style.alignSelf = 'flex-start';
                      tail.style.maxWidth = `${Math.max(132, Math.floor(headerRect.width * 0.34))}px`;
                      tail.style.minWidth = tail.style.minWidth || '92px';

                      if (tail.classList.contains('corner-cluster') || tail.querySelector('.page-tag, .meta-chip, [class*="chip"], [class*="tag"]')) {
                        tail.style.display = 'grid';
                        tail.style.justifyItems = 'end';
                        tail.style.rowGap = tail.style.rowGap || '10px';
                      }

                      const textNodes = Array.from(
                        lead.querySelectorAll('h1, h2, h3, p, .title, .subtitle')
                      ).filter((node) => node instanceof win.HTMLElement);

                      const tailNodes = Array.from(
                        tail.querySelectorAll('.page-tag, .meta-chip, [class*="chip"], [class*="tag"], [class*="badge"]')
                      ).filter((node) => node instanceof win.HTMLElement);

                      textNodes.forEach((node) => {
                        node.style.width = '100%';
                        node.style.maxWidth = '100%';
                        node.style.minWidth = '0';

                        const computed = win.getComputedStyle(node);
                        const fontSize = clampPx(computed.fontSize);
                        const lineHeight = clampPx(computed.lineHeight, fontSize * 1.08);

                        if (node.matches('h1, .title')) {
                          node.style.whiteSpace = 'normal';
                          node.style.wordBreak = 'break-word';
                          node.style.lineHeight = `${Math.max(lineHeight, fontSize * 1.1)}px`;

                          const letterSpacing = clampPx(computed.letterSpacing);
                          if (letterSpacing < -0.6) {
                            node.style.letterSpacing = '-0.4px';
                          }
                        } else if (node.matches('p, .subtitle')) {
                          node.style.lineHeight = `${Math.max(lineHeight, fontSize * 1.2)}px`;
                        }
                      });

                      tailNodes.forEach((node) => {
                        node.style.whiteSpace = 'nowrap';
                        node.style.minWidth = node.classList.contains('page-tag') ? '68px' : (node.style.minWidth || '0');
                        node.style.paddingLeft = node.style.paddingLeft || '10px';
                        node.style.paddingRight = node.style.paddingRight || '10px';
                        if (node.classList.contains('page-tag')) {
                          node.style.display = 'inline-flex';
                          node.style.alignItems = 'center';
                          node.style.justifyContent = 'center';
                        }
                      });
                    };

                    Array.from(doc.querySelectorAll('header')).forEach((header) => {
                      if (header instanceof win.HTMLElement) {
                        stabilizeHeader(header);
                      }
                    });
                  }

                  async function waitForIframeReady(iframe) {
                    await new Promise((resolve, reject) => {
                      const timer = setTimeout(() => resolve(), 6000);
                      iframe.onload = () => {
                        clearTimeout(timer);
                        resolve();
                      };
                      iframe.onerror = (err) => {
                        clearTimeout(timer);
                        reject(err || new Error('iframe load failed'));
                      };
                    });
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (!doc || !doc.body) {
                      throw new Error('Unable to access iframe content');
                    }
                    if (doc.fonts && doc.fonts.ready) {
                      try { await Promise.race([doc.fonts.ready, new Promise(r => setTimeout(r, 1800))]); } catch (_) {}
                    }
                    const images = Array.from(doc.images || []).filter((img) => !img.complete);
                    if (images.length) {
                      await Promise.race([
                        Promise.all(images.map((img) => new Promise((resolve) => {
                          img.onload = img.onerror = () => resolve();
                        }))),
                        new Promise((resolve) => setTimeout(resolve, 2400))
                      ]);
                    }
                    stabilizeLayoutForPpt(doc);
                    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    return doc.body;
                  }

                  const slideElementStream = (async function* () {
                    for (const slide of payload.slides) {
                      const iframe = document.createElement('iframe');
                      iframe.style.cssText = 'width:1280px;height:720px;border:none;position:absolute;left:0;top:0;';
                      iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
                      host.appendChild(iframe);
                      iframe.srcdoc = slide.html;
                      const root = await waitForIframeReady(iframe);
                      try {
                        yield root;
                      } finally {
                        iframe.remove();
                      }
                    }
                  })();

                  const blob = await window.domToPptx.exportToPptx(slideElementStream, {
                    fileName: payload.fileName,
                    skipDownload: true,
                    svgAsVector: false,
                  });

                  const bytes = new Uint8Array(await blob.arrayBuffer());
                  let binary = '';
                  const chunkSize = 0x8000;
                  for (let i = 0; i < bytes.length; i += chunkSize) {
                    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
                  }
                  host.remove();
                  return btoa(binary);
                }
                """,
                payload,
            )
            browser.close()

        output_path.write_bytes(base64.b64decode(b64))
        return output_path


def build_dom_editable_deck_from_html(
    html_dir: Path,
    out_dir: Path,
    slide_meta: list[dict] | None = None,
    deck_name: str | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = out_dir / "previews"
    preview_dir.mkdir(exist_ok=True)
    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        raise ValueError(f"HTML directory is empty: {html_dir}")

    meta_by_index = {}
    if slide_meta:
        meta_by_index = {item["index"]: item for item in slide_meta if "index" in item}

    slides = []
    html_paths_by_index: dict[int, Path] = {}
    for idx, html_path in enumerate(html_files, start=1):
        meta = meta_by_index.get(idx, {})
        title = meta.get("title", html_path.stem)
        page_role = meta.get("page_role", "summary")
        html = html_path.read_text(encoding="utf-8")
        source_png = preview_dir / f"html-source-{idx:02d}.png"
        source_png.write_bytes(render_html_screenshot(html_path))
        dom_preview_png = preview_dir / f"editable-preview-{idx:02d}.png"
        dom_preview_png.write_bytes(source_png.read_bytes())
        slides.append(
            {
                "index": idx,
                "title": title,
                "page_role": page_role,
                "html": html,
                "html_path": str(html_path),
                "preview_png_path": str(dom_preview_png),
                "html_preview_png_path": str(source_png),
            }
        )
        html_paths_by_index[idx] = html_path

    deck_stem = (deck_name or html_dir.parent.name)[:30]
    ppt_path = out_dir.parent / f"{deck_stem}_editable.pptx"
    DomPptxExporter().export_slides(slides, ppt_path)
    audit = _audit_exported_pptx(ppt_path, slides)
    if audit["failures"]:
        ppt_path.unlink(missing_ok=True)
        raise RuntimeError("DOM editable export audit failed: " + " | ".join(audit["failures"]))

    slide_status = {}
    manifest_slides = []
    for slide_result in audit["slides"]:
        idx = int(slide_result["index"])
        slide_payload = slides[idx - 1]
        html_path = html_paths_by_index[idx]
        review_path = _write_dom_review(out_dir, slide_result, html_path)
        status_key = f"{idx:02d}"
        validation_status = "dom-verified" if slide_result["status"] == "pass" else "dom-verified-warn"
        review_status = "PASS" if slide_result["status"] == "pass" else "WARN"
        status_payload = {
            "title": slide_payload["title"],
            "page_role": slide_payload["page_role"],
            "validation_status": validation_status,
            "review_status": review_status,
            "review_rounds": 0,
            "export_ready": True,
            "html_path": slide_payload["html_path"],
            "preview_png_path": slide_payload["preview_png_path"],
            "html_preview_png_path": slide_payload["html_preview_png_path"],
            "preview_basis": "dom-source",
            "audit_basis": "pptx-structure",
            "shape_count": slide_result["shape_count"],
            "text_shape_count": slide_result["text_shape_count"],
            "picture_shape_count": slide_result["picture_shape_count"],
            "html_text_node_count": slide_result["html_text_node_count"],
            "audit_reasons": slide_result["reasons"],
            "review_path": str(review_path),
        }
        slide_status[status_key] = status_payload
        manifest_slides.append(
            {
                "index": idx,
                "title": slide_payload["title"],
                "page_role": slide_payload["page_role"],
                "html_path": slide_payload["html_path"],
                "review_path": str(review_path),
                "preview_png_path": slide_payload["preview_png_path"],
                "html_preview_png_path": slide_payload["html_preview_png_path"],
                "export_ready": True,
                "validation_status": validation_status,
                "review_status": review_status,
                "preview_basis": "dom-source",
                "audit_basis": "pptx-structure",
                "shape_count": slide_result["shape_count"],
                "text_shape_count": slide_result["text_shape_count"],
                "picture_shape_count": slide_result["picture_shape_count"],
                "html_text_node_count": slide_result["html_text_node_count"],
                "audit_reasons": slide_result["reasons"],
            }
        )
        if slide_result["status"] == "warn":
            print(
                f"    [audit] slide {idx:02d} has DOM export warning: "
                + "; ".join(slide_result["reasons"])
            )

    write_slide_status(out_dir, slide_status)
    (out_dir / "editable-export-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": _utc_now_iso(),
                "pipeline": "landppt-dom-export",
                "source_of_truth": "html",
                "html_dir": str(html_dir),
                "pptx_path": str(ppt_path),
                "slide_status_path": str(out_dir / "slide-status.json"),
                "preview_dir": str(preview_dir),
                "audit_summary": audit["summary"],
                "slides": manifest_slides,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ppt_path
