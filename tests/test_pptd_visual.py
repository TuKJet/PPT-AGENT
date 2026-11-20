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

    def test_build_comparison_is_hash_manifest_and_pending_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            rendered = root / "rendered.png"
            Image.new("RGB", (320, 180), "white").save(source)
            Image.new("RGB", (320, 180), "black").save(rendered)
            output = root / "review.jpg"
            result = visual.build_comparison(root, {"01": source}, {"01": rendered}, output)
            self.assertEqual(result["status"], "pending_visual_review")
            self.assertTrue(output.is_file())
            self.assertTrue(Path(result["manifest"]).is_file())
            self.assertEqual(result["pairs"][0]["key"], "01")
            self.assertNotEqual(result["pairs"][0]["source_sha256"], result["pairs"][0]["rendered_sha256"])

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
            page["elements"].append({
                "elementId": "trend", "elementType": "chart", "bounds": [380, 130, 550, 350],
                "data": {"cols": ["Month", "Hours"], "rows": [["Jan", -2], ["Feb", 0], ["Mar", None]]},
                "series": [{"type": "line", "name": "Hours", "lineColor": "#F2A900",
                            "encode": {"x": "Month", "y": "Hours"}}],
            })
            (root / "pages/01.page").write_text(json.dumps(page))
            updated = visual.export_images(root, force=True)
            self.assertNotEqual(updated["source_sha256"], summary["source_sha256"])
            with Image.open(root / ".qa-images/pages/001.png") as image:
                pixels = image.convert("RGB").resize((480, 270))
                yellow = sum(n for n, (r, g, b) in pixels.getcolors(pixels.width * pixels.height)
                             if r > 150 and g > 100 and b < 70)
                self.assertGreater(yellow, 0, "The first page is missing its amber chart series")
            with Image.open(root / ".qa-images/pages/002.png") as image:
                self.assertGreater(ImageStat.Stat(image.convert("RGB")).mean[1], 240)


if __name__ == "__main__":
    unittest.main()
