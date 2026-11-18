from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".codex/skills/ppt-deck-workflow/scripts"))
from pptx_template import TemplateError, export, inventory


def _make_fixture(path: Path) -> dict[str, int]:
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[6])
    text_box = first.shapes.add_textbox(Inches(1), Inches(0.5), Inches(5), Inches(0.6))
    paragraph = text_box.text_frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = "Q3"
    run.font.bold = True
    run.font.size = Pt(24)
    run = paragraph.add_run()
    run.text = " revenue"
    run.font.italic = True

    table = first.shapes.add_table(3, 2, Inches(1), Inches(1.5), Inches(4), Inches(1.4)).table
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Q3"
    table.cell(1, 0).text = "Revenue"
    table.cell(1, 1).text = "10"
    table.cell(2, 0).text = "Margin"
    table.cell(2, 1).text = "20%"

    data = CategoryChartData()
    data.categories = ["Q1", "Q2", "Q3", "Q4"]
    data.add_series("Revenue", (7, 8, 10, 11))
    chart_shape = first.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(3.2), Inches(6), Inches(3), data
    )

    second = prs.slides.add_slide(prs.slide_layouts[6])
    second.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(0.5)).text = "Keep this page"
    prs.save(path)
    return {"text": text_box.shape_id, "table": table._graphic_frame.shape_id, "chart": chart_shape.shape_id}


class TemplatePptxTests(unittest.TestCase):
    def test_inventory_targeted_text_table_and_format_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            ids = _make_fixture(source)
            report = inventory(source)
            self.assertEqual(len(report["slides"]), 2)
            self.assertEqual({item["kind"] for item in report["slides"][0]["objects"]}, {"text", "table", "chart"})

            target = root / "updated.pptx"
            export(source, [
                {"slide": 1, "shape_id": ids["text"], "text": "Q4 revenue", "expected": "Q3 revenue"},
                {"slide": 1, "shape_id": ids["table"], "cell": "B2", "value": "12", "expected": "10"},
            ], target)
            prs = Presentation(target)
            self.assertEqual("Q4 revenue", "".join(run.text for run in prs.slides[0].shapes[0].text_frame.paragraphs[0].runs))
            self.assertEqual("12", prs.slides[0].shapes[1].table.cell(1, 1).text)
            self.assertTrue(prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0].font.bold)
            self.assertGreaterEqual(prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0].font.size.pt, 23)
            self.assertEqual(" revenue", prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[1].text)
            self.assertTrue(prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[1].font.italic)

    def test_chart_update_changes_chart_and_workbook_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            ids = _make_fixture(source)
            before = _zip_hashes(source)
            target = root / "updated.pptx"
            export(source, [{"slide": 1, "shape_id": ids["chart"], "series": 0, "point": 2, "value": 12, "expected": 10}], target)
            after = _zip_hashes(target)
            changed = {name for name in before if before[name] != after.get(name)}
            self.assertTrue(any(name.startswith("ppt/charts/chart") for name in changed))
            self.assertTrue(any(name.startswith("ppt/embeddings/") and name.endswith(".xlsx") for name in changed))
            self.assertNotIn("ppt/slides/slide2.xml", changed)

    def test_expected_mismatch_never_writes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            ids = _make_fixture(source)
            target = root / "updated.pptx"
            with self.assertRaises(TemplateError):
                export(source, [{"slide": 1, "shape_id": ids["text"], "text": "Q4", "expected": "Q2 revenue"}], target)
            self.assertFalse(target.exists())

    def test_second_round_uses_new_expected_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            ids = _make_fixture(source)
            first = root / "first.pptx"
            second = root / "second.pptx"
            export(source, [{"slide": 1, "shape_id": ids["table"], "cell": "B2", "value": "12", "expected": "10"}], first)
            export(first, [{"slide": 1, "shape_id": ids["table"], "cell": "B2", "value": "13", "expected": "12"}], second)
            self.assertEqual("13", Presentation(second).slides[0].shapes[1].table.cell(1, 1).text)


def _zip_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}


if __name__ == "__main__":
    unittest.main()
