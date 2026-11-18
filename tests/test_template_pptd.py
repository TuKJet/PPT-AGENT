from __future__ import annotations
import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUNTIME = ROOT / ".codex" / "skills" / "ppt-deck-workflow" / "scripts"
sys.path.insert(0, str(RUNTIME))
import pptd_template

class TemplatePptdTests(unittest.TestCase):
    def make_project(self, root: Path):
        (root / "pages").mkdir(parents=True); (root / "media").mkdir()
        (root / "media" / "logo.png").write_bytes(b"logo")
        (root / "deck.pptd").write_text("version: v2\ntitle: Group\nsize: [960, 540]\npages:\n  - pages/a.page\n  - pages/b.page\n", encoding="utf-8")
        page = {"pageType": "content", "elements": [
            {"elementId":"title","elementType":"text","bounds":[0,0,100,30],"content":{"text":"Q1","fontSize":20}},
            {"elementId":"table","elementType":"table","bounds":[0,40,100,80],"columnWidths":[.5,.5],"rowHeights":[.5,.5],"rows":[[{"text":"Metric"},{"text":"Q1"}],[{"text":"Revenue"},{"text":"10"}]]},
            {"elementId":"chart","elementType":"chart","bounds":[0,130,100,80],"data":{"cols":["Quarter","Revenue"],"rows":[["Q1",10]]},"series":[{"type":"bar","encode":{"x":"Quarter","y":"Revenue"}}]}
        ]}
        (root/"pages/a.page").write_text(json.dumps(page), encoding="utf-8")
        (root/"pages/b.page").write_text(json.dumps({"pageType":"content","elements":[{"elementId":"keep","elementType":"text","bounds":[0,0,10,10],"content":{"text":"untouched"}}]}), encoding="utf-8")

    def test_inventory_and_real_export(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d)/"source", Path(d)/"out"; self.make_project(source)
            untouched = (source/"pages/b.page").read_bytes()
            report = pptd_template.inventory(source)
            fields = [x["field"] for x in report["pages"][0]["fields"]]
            self.assertIn("rows[1][1].text", fields); self.assertIn("data.rows[0][1]", fields)
            pptd_template.export(source, [
                {"page":1,"element":"title","field":"content.text","expected":"Q1","value":"Q2"},
                {"page":1,"element":"table","field":"rows[1][1].text","expected":"10","value":"12"},
                {"page":1,"element":"chart","field":"data.rows[0][1]","expected":10,"value":12},
            ], dest)
            self.assertEqual((dest/"pages/b.page").read_bytes(), untouched)
            import pptd_runtime as rt
            rt.validate_project(dest)
            if shutil.which("node"):
                report = rt.export_project(dest, Path(d) / "quarter.pptx")
                self.assertEqual(report["zip_integrity"], "passed")

    def test_reject_style_path_and_stale_value_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d)/"source", Path(d)/"out"; self.make_project(source)
            with self.assertRaises(ValueError): pptd_template.export(source,[{"page":1,"element":"title","field":"content.fontSize","expected":20,"value":22}],dest)
            with self.assertRaises(ValueError): pptd_template.export(source,[{"page":1,"element":"title","field":"content.text","expected":"Q0","value":"Q2"}],dest)
            self.assertFalse(dest.exists())

    def test_quarter_expectations_and_rich_text_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source"
            output = Path(d) / "out"
            self.make_project(source)
            changes = [{"page": 1, "element": "chart", "field": "data.rows[0][1]",
                        "expected": 10, "value": 12}]
            pptd_template.export(source, changes, output)
            plan = pptd_template.quarter_expectations(output, changes)
            visual = plan["slides"][0]["plan"]["data_visuals"][0]
            self.assertEqual(visual["editability"], "native_chart")
            self.assertEqual(visual["series"][0]["categories"], ["Q1"])
            self.assertEqual(visual["series"][0]["values"], [12])
            page = json.loads((source / "pages/a.page").read_text())
            page["elements"][0]["content"]["text"] = "<strong>Q1</strong>"
            (source / "pages/a.page").write_text(json.dumps(page))
            with self.assertRaises(ValueError):
                pptd_template.export(source, [{"page": 1, "element": "title",
                                               "field": "content.text",
                                               "expected": "<strong>Q1</strong>",
                                               "value": "<strong>Q2</strong>"}], output)

if __name__ == "__main__": unittest.main()
