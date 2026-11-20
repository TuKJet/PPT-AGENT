from __future__ import annotations

import json
import io
import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from PIL import Image
from pptx import Presentation
import yaml

from test_workflow_helper import init_legacy_run, load_workflow_module, valid_slide_plans


class DataRegionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="data-region-acceptance-")
        self.root = Path(self.tempdir.name).resolve()
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.root.parent)
        self.w = load_workflow_module()
        self.plan = valid_slide_plans(("折线", "line", "content"), ("柱状", "bar", "content"), ("表格", "table", "content"))
        regions = [
            {"id": "trend", "kind": "line", "bounds": [0.08, 0.18, 0.84, 0.62], "data": {"cols": ["月份", "实际", "目标"], "rows": [["一月", -2.5, 0], ["二月", 0, 1.2], ["三月", None, 2.8]]}},
            {"id": "mix", "kind": "bar", "bounds": [0.08, 0.18, 0.84, 0.62], "data": {"cols": ["部门", "本期", "上期"], "rows": [["研发", -12, -8], ["销售", 18, 15], ["运营", 0, 3.5]]}},
            {"id": "table", "kind": "table", "bounds": [0.08, 0.18, 0.84, 0.62], "data": {"cols": ["项目", "本期", "备注"], "rows": [["研发", -12.5, "待确认"], ["销售", 18, "已完成"], ["运营", None, "—"]]}},
        ]
        for slide, region in zip(self.plan["slides"], regions, strict=True):
            slide["plan"]["data_regions"] = [region]
        init_legacy_run(self.w, self.root, topic="数据区域验收", audience="管理层", pages="3", research="")
        self.approve_plan()

    def approve_plan(self):
        self.w.write_json(self.root / "slide-plans.json", self.plan)
        self.w.cmd_preview(Namespace(run_dir=str(self.root), artifact="slide_plans"))
        self.w.cmd_approve(Namespace(run_dir=str(self.root), artifact="slide_plans"))

    def tearDown(self):
        self.tempdir.cleanup()
        if self.previous_output_dir is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output_dir

    def _make_pptd(self):
        root = self.root / "pptd"
        (root / "pages").mkdir(parents=True, exist_ok=True)
        manifest = {"version": "v2", "title": "验收", "size": [1200, 800], "pages": [f"pages/{i:02d}.page" for i in range(1, 4)]}
        (root / "deck.pptd").write_text(json.dumps(manifest), encoding="utf-8")
        for i in range(1, 4):
            (root / "pages" / f"{i:02d}.page").write_text("pageType: content\nelements:\n  - elementId: manual\n    elementType: text\n    bounds: [20, 20, 300, 40]\n    content:\n      text: 人工元素\n", encoding="utf-8")

    def _prepare_img(self):
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.root), renderer="img", source="plans"))
        self.w.prepare_render_jobs(self.root, "img")
        for i, slide in enumerate(self.plan["slides"], 1):
            path = self.w.render_target_path(self.root, "img", i, slide["title"])
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1200, 800), "#E8EEF7").save(path)
        return self.w.export_img(self.root)

    def _assert_pptx_data(self, pptx: Path):
        deck = Presentation(pptx)
        for slide, specification in zip(deck.slides, self.plan["slides"], strict=True):
            region = specification["plan"]["data_regions"][0]
            data = region["data"]
            if region["kind"] == "table":
                table, = [s.table for s in slide.shapes if s.has_table]
                expected = [["" if v is None else str(v) for v in row] for row in [data["cols"], *data["rows"]]]
                self.assertEqual([[c.text for c in row.cells] for row in table.rows], expected)
            else:
                chart, = [s.chart for s in slide.shapes if s.has_chart]
                self.assertEqual([s.name for s in chart.series], data["cols"][1:])
                self.assertEqual(list(chart.plots[0].categories), [row[0] for row in data["rows"]])
                self.assertEqual([s.values for s in chart.series], list(zip(*data["rows"]))[1:])
                self.assertTrue(chart.part.chart_workbook.xlsx_part.blob)

    def _export_pptd(self, source):
        self._make_pptd()
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.root), renderer="pptd", source=source))
        self.w.prepare_render_jobs(self.root, "pptd")
        output = self.w.export_pptd(self.root)
        self._assert_pptx_data(output)
        return output

    def test_direct_pptd_and_img_to_pptd_share_regions_and_are_retry_safe(self):
        direct = self._export_pptd("plans")
        page = self.root / "pptd/pages/03.page"
        first = page.read_text(encoding="utf-8")
        self.w.export_pptd(self.root)
        self.assertEqual(first, page.read_text(encoding="utf-8"))
        self.assertTrue(direct.is_file())
        shutil.rmtree(self.root / "pptd")
        self._prepare_img()
        self._export_pptd("img")
        self.plan["slides"][0]["plan"]["data_regions"] = []
        self.approve_plan()
        self.w.prepare_render_jobs(self.root, "pptd")
        self.w.export_pptd(self.root)
        page_data = yaml.safe_load((self.root / "pptd/pages/01.page").read_text(encoding="utf-8"))
        self.assertFalse(any(e.get("managedDataRegion") for e in page_data["elements"]))

    def test_reserved_img_fills_natively_and_new_artwork_survives_repaint(self):
        slide = self.plan["slides"][0]
        region = slide["plan"]["data_regions"][0]
        region["img"] = "reserve"
        self.approve_plan()
        result = self._prepare_img()
        image = self.w.render_target_path(self.root, "img", 1, slide["title"])
        with Image.open(io.BytesIO(Presentation(result).slides[0].shapes[0].image.blob)) as exported:
            self.assertEqual(len(exported.crop((97, 145, 1103, 638)).getcolors()), 1)
        # This image is the latest generated artwork for a revised slide.
        Image.new("RGB", (1200, 800), "#AA1100").save(image)
        self.w.export_img(self.root)
        with Image.open(image) as painted:
            self.assertEqual(painted.getpixel((3, 4)), (170, 17, 0))
        self._export_pptd("img")


if __name__ == "__main__":
    unittest.main()
