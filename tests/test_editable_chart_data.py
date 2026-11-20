import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pptx import Presentation

from test_pptd_runtime import SCRIPTS, make_project, runtime


def read_cells(blob):
    with ZipFile(io.BytesIO(blob)) as book:
        strings = ["".join(entry.itertext()) for entry in ET.fromstring(book.read("xl/sharedStrings.xml"))]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        cells = {}
        for cell in sheet.findall(".//{*}c"):
            value = cell.findtext("{*}v")
            cells[cell.get("r")] = strings[int(value)] if cell.get("t") == "s" else float(value)
        return cells


@unittest.skipUnless(shutil.which("node"), "PPTD writer requires Node")
class EditableChartTests(unittest.TestCase):
    def test_wasm_line_and_bar_workbooks_match_cached_names_categories_and_values(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "pptd"
            _, page = make_project(project)
            data = {"cols": ["批次", "实际投入", "=预算"], "rows": [["001", -1.25, 0], ["二期", 0, 23.5]]}
            for index, kind in enumerate(("line", "bar")):
                page["elements"].append({
                    "elementType": "chart", "elementId": kind, "bounds": [50 + 450 * index, 120, 400, 275],
                    "data": data, "series": [
                        {"type": kind, "name": col, "encode": {"x": "批次", "y": col}}
                        for col in data["cols"][1:]
                    ],
                })
            (project / "pages/01.page").write_text(json.dumps(page), encoding="utf-8")
            target = Path(tmp) / "result.pptx"
            runtime.export_project(project, target)

            charts = [s.chart for s in Presentation(target).slides[0].shapes if s.has_chart]
            self.assertEqual(len(charts), 2)
            for chart, kind in zip(charts, ("line", "bar")):
                self.assertTrue(chart._chartSpace.xpath(f".//c:{kind}Chart"))
                self.assertEqual([s.name for s in chart.series], data["cols"][1:])
                self.assertEqual([s.values for s in chart.series], [(-1.25, 0.0), (0.0, 23.5)])
                self.assertEqual(list(chart.plots[0].categories), ["001", "二期"])
                self.assertEqual([n.text for n in chart._chartSpace.xpath(".//c:f")], [
                    "ChartData!$B$1", "ChartData!$A$2:$A$3", "ChartData!$B$2:$B$3",
                    "ChartData!$C$1", "ChartData!$A$2:$A$3", "ChartData!$C$2:$C$3",
                ])
                self.assertEqual(read_cells(chart.part.chart_workbook.xlsx_part.blob), {
                    "A1": "Category", "B1": "实际投入", "C1": "=预算", "A2": "001",
                    "B2": -1.25, "C2": 0, "A3": "二期", "B3": 0, "C3": 23.5,
                })
