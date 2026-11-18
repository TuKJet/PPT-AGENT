from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex" / "skills" / "ppt-deck-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from chart_workbook import bind_chart_workbooks
from pptd_runtime import export_project


class ChartWorkbookTests(unittest.TestCase):
    def _create_project(self, root: Path) -> Path:
        project = root / "input"
        pages = project / "pages"
        pages.mkdir(parents=True)
        (project / "deck.pptd").write_text(json.dumps({
            "version": "v2",
            "title": "native chart test",
            "size": [960, 540],
            "pages": ["pages/01.page", "pages/02.page"],
        }), encoding="utf-8")
        chart_page = {
            "pageType": "content",
            "elements": [{
                "elementType": "chart",
                "elementId": "sales",
                "bounds": [40, 80, 700, 360],
                "data": {
                    "cols": ["quarter", "revenue", "cost"],
                    "rows": [["Q1", 12, 4], ["Q2", 15, 5], ["Q3", None, 6]],
                },
                "series": [
                    {"type": "line", "encode": {"x": "quarter", "y": "revenue"}, "name": "营收"},
                    {"type": "line", "encode": {"x": "quarter", "y": "cost"}, "name": "成本"},
                ],
            }],
        }
        (pages / "01.page").write_text(json.dumps(chart_page, ensure_ascii=False), encoding="utf-8")
        (pages / "02.page").write_text(json.dumps({
            "pageType": "content",
            "elements": [{
                "elementType": "text", "elementId": "keep", "bounds": [30, 30, 300, 40],
                "content": {"text": "保留页"},
            }],
        }, ensure_ascii=False), encoding="utf-8")
        return project

    def _native_plan(self, second_value: int = 15) -> list[dict]:
        return [{"index": 1, "plan": {"data_visuals": [{
            "element_id": "sales", "editability": "native_chart",
            "series": [
                {"name": "营收", "categories": ["Q1", "Q2", "Q3"], "values": [12, second_value, None]},
                {"name": "成本", "categories": ["Q1", "Q2", "Q3"], "values": [4, 5, 6]},
            ],
        }]}}]

    def test_wasm_fixture_binds_two_series_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self._create_project(root)
            exported = root / "exported.pptx"
            export_project(project, exported)
            bind_chart_workbooks(exported, self._native_plan())
            with zipfile.ZipFile(exported) as archive:
                chart_name = next(name for name in archive.namelist() if name.startswith("ppt/charts/chart"))
                chart = archive.read(chart_name)
                self.assertIn(b"Data!$B$1", chart)
                self.assertIn(b"Data!$C$1", chart)
                self.assertIn(b"Data!$A$2:$A$4", chart)
                self.assertIn(b"Data!$B$2:$B$4", chart)
                self.assertIn(b"Data!$C$2:$C$4", chart)
                workbook_name = next(name for name in archive.namelist() if name.startswith("ppt/embeddings/") and name.endswith(".xlsx"))
                self.assertGreater(len(archive.read(workbook_name)), 1000)
            before = exported.read_bytes()
            bind_chart_workbooks(exported, self._native_plan())
            self.assertEqual(before, exported.read_bytes())

    def test_visual_declaration_is_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._create_project(Path(directory))
            exported = Path(directory) / "exported.pptx"
            export_project(project, exported)
            before = exported.read_bytes()
            bind_chart_workbooks(exported, [{"index": 1, "plan": {"data_visuals": [{
                "element_id": "sales", "editability": "visual",
            }]}}])
            self.assertEqual(before, exported.read_bytes())

    def test_runtime_native_plan_verifies_then_mismatch_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._create_project(Path(directory))
            exported = Path(directory) / "runtime.pptx"
            export_project(project, exported, slides=self._native_plan())
            original_hash = hashlib.sha256(exported.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                export_project(project, exported, slides=self._native_plan(second_value=16))
            self.assertEqual(original_hash, hashlib.sha256(exported.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
