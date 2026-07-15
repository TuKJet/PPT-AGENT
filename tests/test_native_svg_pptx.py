from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pptx_builder import build_native_svg_pptx


class NativeSvgPptxTests(unittest.TestCase):
    def test_builder_embeds_svg_media_instead_of_only_rasterizing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_dir = root / "svg"
            svg_dir.mkdir()
            (svg_dir / "slide-01.svg").write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
                "<rect width='1280' height='720' fill='#123456'/>"
                "<text x='80' y='120' fill='#ffffff'>Native SVG</text>"
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


if __name__ == "__main__":
    unittest.main()
