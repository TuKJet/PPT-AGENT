from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".codex/skills/ppt-deck-workflow/scripts"))
from visual_plan import VisualPlanError, validate_data_visuals


class VisualPlanTests(unittest.TestCase):
    def test_old_plan_without_optional_field_is_valid(self):
        self.assertEqual(validate_data_visuals({"core_message": "x"})["core_message"], "x")

    def test_valid_native_chart(self):
        plan = {"data_visuals": [{
            "element_id": "sales", "relationship": "change_over_time", "encoding": "line",
            "reason": "让管理层看到季度趋势", "editability": "native_chart",
            "series": [{"name": "营收", "categories": ["Q1", "Q2"], "values": [12, 15]}],
        }]}
        self.assertIs(validate_data_visuals(plan), plan)

    def test_valid_table_and_visual(self):
        plan = {"data_visuals": [
            {"element_id": "budget", "relationship": "budget_execution", "encoding": "native_table",
             "reason": "逐项核对预算与实际", "editability": "native_table",
             "cells": [["项目", "预算"], ["云资源", "12"]]},
            {"element_id": "flow", "relationship": "process_or_structure", "encoding": "visual",
             "reason": "说明审批关系", "editability": "visual"},
        ]}
        validate_data_visuals(plan)

    def test_rejects_duplicates_conflicts_dimensions_and_non_finite(self):
        base = {"element_id": "sales", "relationship": "change_over_time", "encoding": "line",
                "reason": "看趋势", "editability": "native_chart", "categories": ["Q1", "Q2"],
                "series": [{"name": "营收", "categories": ["Q1", "Q2"], "values": [1, 2]}]}
        for bad in (
            [base, {**base}],
            [{**base, "encoding": "native_table"}],
            [{**base, "series": [{"name": "营收", "values": [1]}]}],
            [{**base, "series": [{"name": "营收", "values": [1, math.inf]}]}],
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(VisualPlanError):
                    validate_data_visuals({"data_visuals": bad})


if __name__ == "__main__":
    unittest.main()
