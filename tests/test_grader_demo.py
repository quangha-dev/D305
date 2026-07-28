"""Acceptance tests for the teacher/AI grading entry points."""

import os
import sys
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from app import RUBRIC_EVIDENCE, build_argument_parser
from grader_demo import run_guardrail_checks


class GraderDemoTests(unittest.TestCase):
    def test_default_cli_is_fast_offline_agent_smoke_test(self):
        args = build_argument_parser().parse_args([])
        self.assertEqual(args.mode, "agent")
        self.assertEqual(args.provider, "mock")
        self.assertEqual(args.test, "1")
        self.assertEqual(len(RUBRIC_EVIDENCE), 6)

    def test_all_adversarial_guardrails_pass(self):
        checks = run_guardrail_checks()
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(item["passed"] for item in checks), checks)


if __name__ == "__main__":
    unittest.main()
