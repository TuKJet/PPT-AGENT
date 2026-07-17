from __future__ import annotations

import base64
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image


def load_crop_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".codex"
        / "skills"
        / "ppt-deck-workflow"
        / "scripts"
        / "embed_img_crops.py"
    )
    spec = importlib.util.spec_from_file_location("embed_img_crops", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class EmbedImgCropsTests(unittest.TestCase):
    def test_embeds_a_scaled_source_crop_without_writing_temp_pngs(self) -> None:
        module = load_crop_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "slide.png"
            source = Image.new("RGB", (200, 100), "#ffffff")
            for x in range(40, 80):
                for y in range(20, 60):
                    source.putpixel((x, y), (255, 0, 0))
            source.save(source_path)

            svg_path = root / "slide.svg"
            svg_path.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 50'>"
                "<rect width='100' height='50' fill='#ffffff'/>"
                "<image data-crop-id='logo' x='20' y='10' width='20' height='20'/>"
                "</svg>",
                encoding="utf-8",
            )
            manifest_path = root / "crops.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_image_path": str(source_path),
                        "svg_path": str(svg_path),
                        "canvas": {"width": 100, "height": 50},
                        "crops": [
                            {
                                "id": "logo",
                                "source_box": [20, 10, 20, 20],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output = module.embed_crops(manifest_path)

            tree = ElementTree.parse(output)
            image = next(
                element
                for element in tree.getroot().iter()
                if element.tag.rsplit("}", 1)[-1] == "image"
            )
            href = image.attrib["href"]
            self.assertTrue(href.startswith("data:image/png;base64,"))
            self.assertNotIn("data-crop-id", image.attrib)
            embedded = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1])))
            self.assertEqual(embedded.size, (40, 40))
            self.assertEqual(embedded.getpixel((10, 10))[:3], (255, 0, 0))
            self.assertEqual(list(root.glob("*.png")), [source_path])


if __name__ == "__main__":
    unittest.main()
