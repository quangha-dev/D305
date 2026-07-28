"""One-command acceptance script for teachers and automated graders.

Quick, deterministic grading (no API key):
    python src/grader_demo.py --provider mock

Full autonomous-model grading:
    python src/grader_demo.py --provider openai --write-artifacts

The script exits 0 only when every mandatory technical check passes. External
cross-audit identity/feedback remains a human responsibility and is reported as
an explicit manual item rather than fabricated evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app import (
    MAX_ITERATIONS,
    RUBRIC_EVIDENCE,
    execute_tool,
    run_react_agent,
)
from evaluation import PROJECT_ROOT, audit_submission_files, run_evaluation_suite
from providers import BaseLLMProvider
from tools import AVAILABLE_TOOLS


class RepeatingActionProvider(BaseLLMProvider):
    """Adversarial provider used to prove repeated-action braking."""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            "Thought: Tôi cố tình lặp lại cùng một action.\n"
            "Action: classify_gift_scope\n"
            'Action Input: {"user_text":"Tư vấn quà","has_active_profile":false}'
        )


class IterationBudgetProvider(BaseLLMProvider):
    """Call a different unknown tool per turn to exhaust the iteration budget."""

    def __init__(self) -> None:
        self.turn = 0

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.turn += 1
        return (
            "Thought: Tôi cố tình tiếp tục gọi tool không tồn tại.\n"
            f"Action: unknown_tool_{self.turn}\n"
            'Action Input: {"value":"adversarial-test"}'
        )


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def run_guardrail_checks() -> list[dict[str, Any]]:
    """Exercise executor isolation, repeated actions and iteration budget."""

    unknown = execute_tool("tool_khong_ton_tai", {}, AVAILABLE_TOOLS)
    repeated = run_react_agent(
        "Tư vấn quà",
        RepeatingActionProvider(),
        tool_registry=AVAILABLE_TOOLS,
        max_iterations=3,
        verbose=False,
    )
    iteration_budget = 2
    exhausted = run_react_agent(
        "Tư vấn quà",
        IterationBudgetProvider(),
        tool_registry=AVAILABLE_TOOLS,
        max_iterations=iteration_budget,
        verbose=False,
    )
    return [
        _check("Unknown tool isolation", not unknown.success and "không tồn tại" in (unknown.error or ""), unknown.error or ""),
        _check("Repeated-action brake", repeated.stop_reason == "repeated_action", repeated.stop_reason),
        _check(
            "MAX_ITERATIONS brake",
            exhausted.stop_reason == "max_iterations" and exhausted.steps == iteration_budget,
            f"{exhausted.stop_reason}; iterations={exhausted.steps}/{iteration_budget}; default={MAX_ITERATIONS}",
        ),
    ]


def run_grader(provider_name: str, *, write_artifacts: bool) -> dict[str, Any]:
    """Run every rubric-relevant automated check and return one report."""

    evaluation = run_evaluation_suite(provider_name, write_artifacts=write_artifacts)
    cases = {int(item["id"]): item for item in evaluation["cases"]}
    artifact_checks = audit_submission_files()
    flowchart = (PROJECT_ROOT / "docs" / "hybrid_flowchart.mermaid")
    flowchart_text = flowchart.read_text(encoding="utf-8") if flowchart.exists() else ""

    react_case = cases.get(2, {})
    react_trace = react_case.get("result", {}).get("trace", [])
    react_actions = [event for event in react_trace if event.get("action")]
    has_observations = bool(react_actions) and all(event.get("observation") is not None for event in react_actions)
    memory_case = cases.get(10, {})
    memory_actions = memory_case.get("actions", [])
    injection_case = cases.get(7, {})
    accessibility_case = cases.get(8, {})
    single_gift_case = cases.get(9, {})

    checks = [
        _check("Agentic Fit + machine-readable test design", len(cases) >= 5 and all(item.get("score") for item in cases.values()), f"{len(cases)} cases"),
        _check("Baseline has zero tool calls", all(item.get("baseline", {}).get("tool_calls") == 0 for item in cases.values()), "all baselines=0"),
        _check("ReAct Action → Observation", has_observations, " → ".join(react_case.get("actions", []))),
        _check("Dynamic tool registry", len(AVAILABLE_TOOLS) >= 5 and all(callable(tool) for tool in AVAILABLE_TOOLS.values()), f"{len(AVAILABLE_TOOLS)} callable tools"),
        _check("Logic gate blocks prompt injection", injection_case.get("result", {}).get("stop_reason") == "prompt_injection" and not injection_case.get("actions"), "case #7"),
        _check("Accessibility conflict stops before tools", accessibility_case.get("result", {}).get("stop_reason") == "suitability_answer" and not accessibility_case.get("actions"), "case #8"),
        _check("Single-gift path avoids Top-3 workflow", single_gift_case.get("result", {}).get("stop_reason") == "single_gift_answer" and "search_gift_catalog" not in single_gift_case.get("actions", []), "case #9"),
        _check("Planning evidence", any(event.get("event") == "autonomous_plan" for event in react_trace), "autonomous_plan trace event"),
        _check("Memory feedback evidence", "update_profile_from_feedback" in memory_actions and "rank_and_diversify_gifts" in memory_actions, " → ".join(memory_actions)),
        _check("Hybrid flowchart", "Logic gate" in flowchart_text and "Planning" in flowchart_text and "Recovery" in flowchart_text, str(flowchart.relative_to(PROJECT_ROOT)) if flowchart.exists() else "missing"),
        _check("Unit/integration tests", evaluation["unit_tests"]["success"], evaluation["unit_tests"]["output"].splitlines()[-2] if evaluation["unit_tests"]["output"] else "no output"),
        _check("Required artifacts + Git hygiene", all(item["passed"] for item in artifact_checks), f"{sum(item['passed'] for item in artifact_checks)}/{len(artifact_checks)}"),
        _check("Rubric map in app.py", len(RUBRIC_EVIDENCE) == 6, ", ".join(RUBRIC_EVIDENCE)),
        *run_guardrail_checks(),
    ]
    passed = sum(item["passed"] for item in checks)
    return {
        "provider": provider_name,
        "summary": {
            "technical_checks_passed": passed,
            "technical_checks_total": len(checks),
            "test_cases_passed": evaluation["summary"]["passed_cases"],
            "test_cases_total": evaluation["summary"]["case_count"],
            "average_case_score": evaluation["summary"]["average_score"],
            "manual_cross_audit_required": True,
        },
        "checks": checks,
        "evaluation": evaluation,
    }


def print_report(report: dict[str, Any], *, show_trace: bool) -> None:
    print("=" * 76)
    print("GIFT SENSE · TEACHER/AI GRADER ACCEPTANCE SCRIPT")
    print("=" * 76)
    for item in report["checks"]:
        print(f"[{'PASS' if item['passed'] else 'FAIL'}] {item['name']}: {item['detail']}")
    summary = report["summary"]
    print("-" * 76)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if show_trace:
        case = next(item for item in report["evaluation"]["cases"] if int(item["id"]) == 2)
        print("\nTRACE MẪU — TEST #2")
        print(json.dumps(case["result"]["trace"], ensure_ascii=False, indent=2))
    print("\nMANUAL: Cross-Audit cần tên và phản hồi thật từ nhóm/người chấm chéo.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy một kịch bản nghiệm thu bao phủ toàn bộ rubric GiftSense.")
    parser.add_argument("--provider", choices=("mock", "openai", "gemini", "anthropic", "openrouter"), default="mock")
    parser.add_argument("--write-artifacts", action="store_true", help="Cập nhật trace/checklist trong docs.")
    parser.add_argument("--show-trace", action="store_true", help="In trace đầy đủ của case ReAct mẫu.")
    parser.add_argument("--json", action="store_true", help="In toàn bộ report dạng JSON.")
    args = parser.parse_args()
    report = run_grader(args.provider, write_artifacts=args.write_artifacts)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, show_trace=args.show_trace)
    summary = report["summary"]
    all_technical = summary["technical_checks_passed"] == summary["technical_checks_total"]
    all_cases = summary["test_cases_passed"] == summary["test_cases_total"]
    return 0 if all_technical and all_cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
