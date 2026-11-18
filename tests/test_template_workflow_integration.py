from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex" / "skills" / "ppt-deck-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import workflow


class TemplateWorkflowIntegrationTests(unittest.TestCase):
    def test_approved_pptd_template_keeps_page_order_and_verifies_data_on_export(self):
        from test_workflow_helper import valid_slide_plans
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"OUTPUT_DIR": directory}):
            root = Path(directory)
            project, run = root / "master", root / "quarter"
            project.mkdir()
            workflow.write_json(project / "deck.pptd", {"version": "v2", "pages": ["original.page"]})
            workflow.write_json(project / "original.page", {"elements": [{
                "elementId": "heading", "elementType": "text", "bounds": [50, 5, 400, 24],
                "content": {"text": "Sales"}
            }, {
                "elementId": "ledger", "elementType": "table", "bounds": [50, 30, 400, 80],
                "columnWidths": [1], "rowHeights": [1], "rows": [[{"text": "15"}]]
            }]})
            updates = root / "updates.json"
            workflow.write_json(updates, [{"page": 1, "element": "ledger", "field": "rows[0][0].text",
                                           "expected": "15", "value": "18"}])
            self._run(["init", "--topic", "Quarter", "--run-dir", str(run)])
            plans = valid_slide_plans(("Sales", "Current quarter", "content"))
            plans["version"] = 3
            plans["deck_strategy"]["use_context"] = "standalone"
            plans["slides"][0]["plan"]["copy_layers"] = {"on_screen": ["Sales"], "talk_track": [], "reference": []}
            visual = {"element_id": "ledger", "editability": "native_table", "relationship": "budget_execution",
                      "encoding": "table", "reason": "Compare exact approved spending", "cells": [["18"]]}
            plans["slides"][0]["plan"]["data_visuals"] = [copy.deepcopy(visual)]
            args = ["apply-pptd-template", "--template", str(project), "--changes", str(updates), "--run-dir", str(run)]
            with self.assertRaisesRegex(RuntimeError, "approved"):
                self._run(args)
            for kind, data in [("outline", {"pages": [{"title": "Sales"}]}), ("contents", {"Sales": "Current quarter"}),
                               ("slide_plans", plans)]:
                workflow.write_json(run / workflow.ARTIFACT_FILES[kind], data)
                self._run(["preview", "--artifact", kind, "--run-dir", str(run)])
                self._run(["approve", "--artifact", kind, "--run-dir", str(run)])
            preview = (run / ".workflow/slide-plans-preview.md").read_text(encoding="utf-8")
            self.assertIn(visual["reason"], preview)
            for renderer in ("img", "pptd"):
                self._run(["choose-renderer", "--renderer", renderer, "--run-dir", str(run)])
                self._run(["prepare-render-jobs", "--run-dir", str(run)])
                job = workflow.read_json(run / "render-jobs" / renderer / "slide-01.json")
                self.assertEqual(job["plan"]["data_visuals"], [visual])
            self._run(args)
            self.assertTrue((run / "pptd/original.page").exists())
            self._run(["export", "--run-dir", str(run)])
            self._run(["finalize", "--apply", "--run-dir", str(run)])
            receipt, = workflow.read_json(run / "slide-plans.json")["_delivery"]["verified_objects"]
            self.assertEqual((receipt["element_id"], receipt["status"]), ("ledger", "passed"))
    def _make_template(self, path: Path) -> dict[str, int]:
        prs = Presentation()
        first = prs.slides.add_slide(prs.slide_layouts[6])
        title = first.shapes.add_textbox(Inches(1), Inches(0.5), Inches(6), Inches(0.5))
        title.text = "集团季度经营简报 Q3"
        value = first.shapes.add_textbox(Inches(1), Inches(1.5), Inches(3), Inches(0.5))
        value.text = "营收 120"
        second = prs.slides.add_slide(prs.slide_layouts[6])
        second.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(0.5)).text = "保留的集团模板页"
        prs.save(path)
        return {"title": title.shape_id, "value": value.shape_id}

    def _run(self, argv: list[str]) -> str:
        parser = workflow.build_parser()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            args = parser.parse_args(argv)
            args.func(args)
        return output.getvalue()

    def test_template_inventory_and_update_keep_master_and_other_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "group-template.pptx"
            target = root / "q4-update" / "q4-update.pptx"
            ids = self._make_template(source)
            changes = root / "changes.json"
            changes.write_text(json.dumps([
                {"slide": 1, "shape_id": ids["title"], "text": "集团季度经营简报 Q4", "expected": "集团季度经营简报 Q3"},
                {"slide": 1, "shape_id": ids["value"], "text": "营收 138", "expected": "营收 120"},
            ], ensure_ascii=False), encoding="utf-8")

            inventory_output = self._run(["template-inventory", "--template", str(source)])
            inventory = json.loads(inventory_output)
            self.assertEqual(inventory["slides"][0]["slide"], 1)
            self.assertEqual(inventory["slides"][1]["slide"], 2)

            with patch.dict("os.environ", {"OUTPUT_DIR": str(root)}):
                self._run(["template-update", "--template", str(source), "--changes", str(changes), "--run-dir", str(target.parent)])
            updated = Presentation(target)
            self.assertEqual("集团季度经营简报 Q4", updated.slides[0].shapes[0].text)
            self.assertEqual("营收 138", updated.slides[0].shapes[1].text)
            self.assertEqual("保留的集团模板页", updated.slides[1].shapes[0].text)
            self.assertEqual(len(updated.slide_masters), len(Presentation(source).slide_masters))
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(target) as after:
                self.assertEqual(before.read("ppt/slideMasters/slideMaster1.xml"), after.read("ppt/slideMasters/slideMaster1.xml"))
                self.assertEqual(before.read("ppt/slides/slide2.xml"), after.read("ppt/slides/slide2.xml"))

    def test_stale_expected_value_does_not_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "group-template.pptx"
            target = root / "previous" / "previous.pptx"
            target.parent.mkdir()
            ids = self._make_template(source)
            target.write_bytes(b"previous-deliverable")
            changes = root / "stale.json"
            changes.write_text(json.dumps([{"slide": 1, "shape_id": ids["value"], "text": "营收 138", "expected": "营收 999"}], ensure_ascii=False), encoding="utf-8")
            with patch.dict("os.environ", {"OUTPUT_DIR": str(root)}):
                with self.assertRaises(FileExistsError):
                    self._run(["template-update", "--template", str(source), "--changes", str(changes), "--run-dir", str(target.parent)])
                with self.assertRaisesRegex(ValueError, "expected"):
                    self._run(["template-update", "--template", str(source), "--changes", str(changes), "--run-dir", str(root / "attempt")])
                self.assertFalse((root / "attempt").exists())
            self.assertEqual(target.read_bytes(), b"previous-deliverable")


if __name__ == "__main__":
    unittest.main()
