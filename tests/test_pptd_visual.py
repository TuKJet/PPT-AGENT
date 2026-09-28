from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image, ImageStat
from test_workflow_helper import load_workflow_module
from test_pptd_runtime import make_project

load_workflow_module()
import pptd_visual as visual


class PPTDVisualTests(unittest.TestCase):
    def test_archive_order_and_count_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = io.BytesIO()
            Image.new("RGB", (16, 9), "red").save(data, format="PNG")
            archive_path = root / "images.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nested/2.png", data.getvalue())
                archive.writestr("nested/1.png", data.getvalue())
            with self.assertRaisesRegex(ValueError, "order/count"):
                visual.unpack_pages(archive_path, root / "bad", 3)
            paths = visual.unpack_pages(archive_path, root / "pages", 2)
            self.assertEqual([p.name for p in paths], ["001.png", "002.png"])

    def test_fingerprint_covers_media_and_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, page = make_project(root)
            first = visual.build_payload(root)[2]
            page["elements"][0]["content"]["text"] = "Updated"
            (root / "pages/01.page").write_text(json.dumps(page))
            self.assertNotEqual(first, visual.build_payload(root)[2])
            (root / "media").mkdir()
            media = root / "media/picture.png"
            Image.new("RGB", (16, 9), "red").save(media)
            page["elements"].append({"elementId": "photo", "elementType": "image",
                                     "bounds": [0, 300, 100, 100], "src": "media/picture.png"})
            (root / "pages/01.page").write_text(json.dumps(page))
            before = visual.build_payload(root)[2]
            Image.new("RGB", (16, 9), "blue").save(media)
            self.assertNotEqual(before, visual.build_payload(root)[2])

    def test_real_editor_exports_all_pages_and_overview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, page = make_project(root)
            second = {"elements": [{"elementId": "background", "elementType": "shape",
                                     "bounds": [0, 0, 960, 540], "shapeName": "rect",
                                     "fill": {"type": "solid", "color": "#FF0000"}}]}
            (root / "pages/02.page").write_text(json.dumps(second))
            manifest["pages"].append("pages/02.page")
            (root / "deck.pptd").write_text(json.dumps(manifest))
            summary = visual.export_images(root)
            self.assertEqual(summary["page_count"], 2)
            self.assertEqual(summary["images"][1]["page"], "pages/02.page")
            self.assertEqual(summary["visual_review"], "pending")
            with Image.open(root / ".qa-images/pages/002.png") as image:
                rgb = ImageStat.Stat(image.convert("RGB")).mean
                self.assertGreater(rgb[0], 240)
                self.assertLess(rgb[1], 20)
            with Image.open(summary["overview"]) as image:
                self.assertEqual(image.width, 1316)
            with self.assertRaisesRegex(ValueError, "--force"):
                visual.export_images(root)
            second["elements"][0]["fill"]["color"] = "#00FF00"
            (root / "pages/02.page").write_text(json.dumps(second))
            updated = visual.export_images(root, force=True)
            self.assertNotEqual(updated["source_sha256"], summary["source_sha256"])
            with Image.open(root / ".qa-images/pages/002.png") as image:
                self.assertGreater(ImageStat.Stat(image.convert("RGB")).mean[1], 240)


if __name__ == "__main__":
    unittest.main()
