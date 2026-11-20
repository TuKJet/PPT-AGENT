from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".codex/skills/ppt-deck-workflow/scripts"))
from region_artwork import draw_image  # noqa: E402


REGIONS = [
    {"id": "line", "kind": "line", "bounds": [0.03, 0.05, 0.29, 0.88],
     "data": {"cols": ["月份", "收入", "成本"], "rows": [["1月", 4, 1], ["2月", -2, 3], ["3月", None, 0], ["4月", 5, -1]]}},
    {"id": "bar", "kind": "bar", "bounds": [0.355, 0.05, 0.29, 0.88],
     "data": {"cols": ["部门", "实际", "目标"], "rows": [["甲", 4, 2], ["乙", -3, 1], ["丙", 0, -2], ["丁", None, 3]]}},
    {"id": "table", "kind": "table", "bounds": [0.68, 0.05, 0.29, 0.88],
     "data": {"cols": ["月份", "收入", "备注"], "rows": [["1月", 4, "正常"], ["2月", -2, "调整"], ["3月", None, "待补"]]}},
]


class RegionArtworkTests(unittest.TestCase):
    def test_same_size_and_regions_are_clipped(self):
        image = Image.new("RGB", (1200, 675), "#DDE5F0")
        result = draw_image(image, REGIONS)
        self.assertEqual(result.size, image.size)
        self.assertEqual(result.mode, image.mode)
        self.assertNotEqual(result.getpixel((100, 100)), image.getpixel((100, 100)))

    def test_missing_value_breaks_line_without_replacing_it_with_zero(self):
        image = Image.new("RGB", (500, 240), "white")
        region = {"kind": "line", "bounds": [0, 0, 1, 1], "data": {
            "cols": ["期", "值"], "rows": [["A", 3], ["B", None], ["C", 3]]}}
        colors = ("#102030",)
        gap = draw_image(image, [region], colors)
        region["data"]["rows"][1][1] = 3
        line = draw_image(image, [region], colors)
        # Only the connected series crosses the middle category at plot height.
        mid = (245, 22, 295, 100)
        self.assertNotIn((16, 32, 48), gap.crop(mid).getdata())
        self.assertIn((16, 32, 48), line.crop(mid).getdata())

    def test_reserved_img_panel_covers_source_art_and_keeps_surrounding_pixels(self):
        image = Image.new("RGB", (900, 500), "red")
        result = draw_image(image, [dict(REGIONS[0], img="reserve")], {"surface": "#EFEFEF"})
        self.assertEqual(result.getpixel((60, 250)), (239, 239, 239))
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))

    def test_custom_palette_changes_artwork(self):
        image = Image.new("RGB", (900, 500), "white")
        blue = draw_image(image, [REGIONS[1]], palette=("#111111", "#222222"))
        red = draw_image(image, [REGIONS[1]], palette=("#AA0000", "#00AA00"))
        self.assertNotEqual(blue.tobytes(), red.tobytes())

    def test_named_palette_dict_is_supported(self):
        image = Image.new("RGB", (900, 500), "white")
        palette = {"background": "#F8FAFC", "surface": "#FFFDF8", "primary": "#4C1D95",
                   "accent": "#C2410C", "text_primary": "#1E1B4B", "text_muted": "#64748B"}
        result = draw_image(image, [REGIONS[0]], palette)
        self.assertNotEqual(result.tobytes(), image.tobytes())


if __name__ == "__main__":
    unittest.main()
