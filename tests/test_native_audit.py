import json
import sys
import io
import zipfile
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".codex/skills/ppt-deck-workflow/scripts"))
from native_audit import verify_native_objects


class NativeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        (self.project / "pages").mkdir(parents=True)
        (self.project / "deck.pptd").write_text(json.dumps({"version": "v2", "pages": ["pages/01.page"]}), encoding="utf-8")
        self.pptx = self.root / "deck.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        chart_data = CategoryChartData()
        chart_data.categories = ["Q1", "Q2"]
        chart_data.add_series("营收", (12, 15))
        chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE, 0, 0, 3000000, 2000000, chart_data)
        chart.name = "sales"
        table = slide.shapes.add_table(2, 2, 3500000, 0, 2000000, 1500000)
        table.name = "ledger"
        table.table.cell(0, 0).text = "季度"
        table.table.cell(0, 1).text = "营收"
        table.table.cell(1, 0).text = "Q2"
        table.table.cell(1, 1).text = "15"
        prs.save(self.pptx)
        page = {"elements": [{"elementId": "sales", "elementType": "chart"}, {"elementId": "ledger", "elementType": "table"}]}
        (self.project / "pages/01.page").write_text(json.dumps(page), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_chart_and_table_pass(self):
        reports = verify_native_objects(self.pptx, self.project, [{"index": 1, "plan": {"data_visuals": [
            {"element_id": "sales", "editability": "native_chart", "series": [{"name": "营收", "categories": ["Q1", "Q2"], "values": [12, 15]}]},
            {"element_id": "ledger", "editability": "native_table", "cells": [["季度", "营收"], ["Q2", "15"]]},
        ]}}])
        self.assertEqual([record["status"] for record in reports], ["passed", "passed"])

    def test_wrong_workbook_value_is_rejected(self):
        # Keep the chart cache intact and corrupt only the embedded worksheet.
        with zipfile.ZipFile(self.pptx) as z:
            parts = {n: z.read(n) for n in z.namelist()}
        name = next(n for n in parts if n.endswith(".xlsx"))
        with zipfile.ZipFile(io.BytesIO(parts[name])) as wb:
            sheets = {n: wb.read(n) for n in wb.namelist()}
        sheet = "xl/worksheets/sheet1.xml"
        self.assertIn(b"<v>15</v>", sheets[sheet])
        sheets[sheet] = sheets[sheet].replace(b"<v>15</v>", b"<v>99</v>")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as wb:
            for n, data in sheets.items():
                wb.writestr(n, data)
        parts[name] = buffer.getvalue()
        with zipfile.ZipFile(self.pptx, "w") as z:
            for n, data in parts.items():
                z.writestr(n, data)
        reports = verify_native_objects(self.pptx, self.project, [{"index": 1, "plan": {"data_visuals": [
            {"element_id": "sales", "editability": "native_chart", "series": [{"name": "营收", "categories": ["Q1", "Q2"], "values": [12, 15]}]},
        ]}}])
        self.assertEqual(reports[0]["status"], "failed")

    def test_category_and_wrong_object_fail(self):
        reports = verify_native_objects(self.pptx, self.project, [{"index": 1, "plan": {"data_visuals": [
            {"element_id": "sales", "editability": "native_chart", "series": [{"name": "营收", "categories": ["Q2", "Q1"], "values": [12, 15]}]},
            {"element_id": "ledger", "editability": "native_chart", "series": []},
        ]}}])
        self.assertEqual([record["status"] for record in reports], ["failed", "failed"])

    def test_no_expectations_and_visual_are_noop(self):
        self.assertEqual(verify_native_objects(self.pptx, self.project, [{"index": 1}]), [])
        self.assertEqual(verify_native_objects(self.pptx, self.project, [{"index": 1, "plan": {"data_visuals": [{"element_id": "sales", "editability": "visual"}]}}]), [])

    def test_source_element_absence_is_reported(self):
        reports = verify_native_objects(self.pptx, self.project, [{"index": 1, "plan": {"data_visuals": [
            {"element_id": "missing", "editability": "native_table", "cells": [["x"]]},
        ]}}])
        self.assertEqual(reports[0]["status"], "failed")
        self.assertIn("absent from the PPTD source", reports[0]["errors"][0])


if __name__ == "__main__":
    unittest.main()
