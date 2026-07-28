"""Tests for automated rubric scoring and submission artifact checks."""

import os
import sys
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from app import AgentResult
from evaluation import audit_submission_files, load_editable_test_cases, score_agent_result


class EvaluationTests(unittest.TestCase):
    def test_machine_readable_checks_score_safe_zero_tool_case(self):
        case = {
            "checks": {
                "stop_reasons": ["suitability_answer"],
                "answer_contains": ["không nên"],
                "forbidden_tools": ["search_gift_catalog"],
                "max_tools": 0,
            }
        }
        result = AgentResult(
            True,
            "Không nên chọn món quà này.",
            "suitability_answer",
            1,
            [{"event": "logic_precheck", "stopped_before_tools": True}],
        )
        score = score_agent_result(case, result)
        self.assertEqual(score["total"], 8)
        self.assertTrue(score["passed"])

    def test_config_and_required_artifacts_are_machine_checkable(self):
        cases = load_editable_test_cases()
        self.assertGreaterEqual(len(cases), 5)
        self.assertTrue(all(case.get("checks") for case in cases))
        checks = audit_submission_files()
        self.assertTrue(all(item["passed"] for item in checks))


if __name__ == "__main__":
    unittest.main()
