from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pptx_builder import _svg_signature, _validate_native_svg_package, build_native_svg_pptx


class NativeSvgPptxTests(unittest.TestCase):
    @staticmethod
    def _write_package(root: Path, slide_count: int, targets: list[str], media: dict[str, str]) -> Path:
        output = root / "fixture.pptx"
        with zipfile.ZipFile(output, "w") as archive:
            for index in range(1, slide_count + 1):
                archive.writestr(
                    f"ppt/slides/slide{index}.xml",
                    f"<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' "
                    "xmlns:asvg='http://schemas.microsoft.com/office/drawing/2016/SVG/main' "
                    "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
                    f"<asvg:svgBlip r:embed='rId1'/></p:sld>",
                )
                archive.writestr(
                    f"ppt/slides/_rels/slide{index}.xml.rels",
                    "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                    f"<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image' "
                    f"Target='../media/{targets[index - 1]}'/></Relationships>",
                )
            for name, content in media.items():
                archive.writestr(f"ppt/media/{name}", content)
        return output
    def test_builder_embeds_svg_media_instead_of_only_rasterizing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg"
            svg_dir.mkdir()
            (svg_dir / "slide-01.svg").write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
                "<rect width='1280' height='720' fill='#123456'/>"
                "<text x='80' y='120' fill='#ffffff'>Native SVG</text>"
                "<image x='80' y='160' width='32' height='32' "
                "href='data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='/>"
                "</svg>",
                encoding="utf-8",
            )
            output = root / "native-svg.pptx"

            build_native_svg_pptx(svg_dir, output)

            self.assertTrue(output.exists())
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.startswith("ppt/media/") and name.endswith(".svg") for name in names))
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
                self.assertIn("svgBlip", slide_xml)

    def test_builder_preserves_explicit_svg_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.svg"
            second = root / "second.svg"
            first.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#112233'/></svg>",
                encoding="utf-8",
            )
            second.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#aabbcc'/></svg>",
                encoding="utf-8",
            )

            output = root / "ordered.pptx"
            build_native_svg_pptx(root / "missing-directory", output, svg_paths=[second, first])

            with zipfile.ZipFile(output) as archive:
                slide1_svg = archive.read("ppt/media/image-1-2.svg").decode("utf-8")
                slide2_svg = archive.read("ppt/media/image-2-2.svg").decode("utf-8")
                self.assertIn("#aabbcc", slide1_svg)
                self.assertIn("#112233", slide2_svg)

    def test_package_validation_rejects_non_root_dimension_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = "<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height='20'/></svg>"
            changed = "<svg xmlns='http://www.w3.org/2000/svg'><rect width='11' height='20'/></svg>"
            output = self._write_package(root, 1, ["image-1.svg"], {"image-1.svg": changed})
            with self.assertRaisesRegex(RuntimeError, "order/content"):
                _validate_native_svg_package(output, [source])

    def test_package_validation_rejects_changed_svg_tail_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = "<svg xmlns='http://www.w3.org/2000/svg'><text>Hi</text>after</svg>"
            changed = "<svg xmlns='http://www.w3.org/2000/svg'><text>Hi</text>altered</svg>"
            output = self._write_package(root, 1, ["image-1.svg"], {"image-1.svg": changed})
            with self.assertRaisesRegex(RuntimeError, "order/content"):
                _validate_native_svg_package(output, [source])

    def test_signature_allows_exporter_style_formatting_and_root_dimensions(self) -> None:
        source = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' "
            "style='fill:#123456'><rect width='10' height='20' "
            "style='fill:#abc;stroke-width: 2'/></svg>"
        )
        exported = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' "
            "style='fill: rgb(18, 52, 86); stroke:none'>"
            "<rect width='10' height='20' style='fill: rgb(170, 187, 204); "
            "stroke-width:2; opacity:1'/></svg>"
        )
        self.assertEqual(_svg_signature(source), _svg_signature(exported, source))

    def test_package_validation_rejects_missing_slide_and_reordered_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = "<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#112233'/></svg>"
            second = "<svg xmlns='http://www.w3.org/2000/svg'><rect fill='#aabbcc'/></svg>"
            missing = self._write_package(root, 1, ["image-1.svg"], {"image-1.svg": first})
            with self.assertRaisesRegex(RuntimeError, "slide count"):
                _validate_native_svg_package(missing, [first, second])

            reordered = self._write_package(
                root, 2, ["image-2.svg", "image-1.svg"],
                {"image-1.svg": first, "image-2.svg": second},
            )
            with self.assertRaisesRegex(RuntimeError, "order/content"):
                _validate_native_svg_package(reordered, [first, second])


if __name__ == "__main__":
    unittest.main()
