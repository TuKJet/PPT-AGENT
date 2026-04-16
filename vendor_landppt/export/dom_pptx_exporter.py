from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from html_pipeline.html_builder import render_html_screenshot, write_slide_status


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    slide_status = {}
    manifest_slides = []
    for idx, html_path in enumerate(html_files, start=1):
        meta = meta_by_index.get(idx, {})
        title = meta.get("title", html_path.stem)
        page_role = meta.get("page_role", "summary")
        html = html_path.read_text(encoding="utf-8")
        source_png = preview_dir / f"html-source-{idx:02d}.png"
        source_png.write_bytes(render_html_screenshot(html_path))
        dom_preview_png = preview_dir / f"editable-preview-{idx:02d}.png"
        dom_preview_png.write_bytes(source_png.read_bytes())
        slides.append({"title": title, "page_role": page_role, "html": html})
        slide_status[f"{idx:02d}"] = {
            "title": title,
            "page_role": page_role,
            "validation_status": "dom-exported",
            "review_status": "PASS",
            "review_rounds": 0,
            "export_ready": True,
            "html_path": str(html_path),
            "preview_png_path": str(dom_preview_png),
            "html_preview_png_path": str(source_png),
            "preview_basis": "dom-source",
        }
        manifest_slides.append(
            {
                "index": idx,
                "title": title,
                "page_role": page_role,
                "html_path": str(html_path),
                "preview_png_path": str(dom_preview_png),
                "html_preview_png_path": str(source_png),
                "export_ready": True,
                "validation_status": "dom-exported",
                "preview_basis": "dom-source",
            }
        )

    deck_stem = (deck_name or html_dir.parent.name)[:30]
    ppt_path = out_dir.parent / f"{deck_stem}_editable.pptx"
    DomPptxExporter().export_slides(slides, ppt_path)
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
                "slides": manifest_slides,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ppt_path
