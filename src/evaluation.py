"""Automated rubric evaluation and submission artifact generation for GiftSense."""

from __future__ import annotations

from datetime import datetime
import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from app import GiftAssistantSession, load_test_cases, run_baseline_chatbot
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "test_cases.json"
TRACE_REPORT_PATH = PROJECT_ROOT / "docs" / "trace_eval.md"
TRACE_JSON_PATH = PROJECT_ROOT / "docs" / "generated_traces.json"
CHECKLIST_PATH = PROJECT_ROOT / "docs" / "submission_checklist.md"
CROSS_AUDIT_PATH = PROJECT_ROOT / "docs" / "cross_audit.md"
GENERATED_START = "<!-- AUTO_EVAL_START -->"
GENERATED_END = "<!-- AUTO_EVAL_END -->"

REQUIRED_ARTIFACTS = (
    "README.md",
    "config/test_cases.json",
    "src/tools.py",
    "src/prompts.py",
    "src/app.py",
    "src/evaluation.py",
    "src/grader_demo.py",
    "src/GRADING_GUIDE.md",
    "docs/trace_eval.md",
    "docs/hybrid_flowchart.mermaid",
    "docs/PHAN_CONG_CONG_VIEC.md",
    "docs/DANH_SACH_DE_TAI.md",
)


def load_editable_test_cases() -> list[dict[str, Any]]:
    """Load raw test-case dictionaries for the UI editor."""

    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_test_cases(cases: list[dict[str, Any]]) -> None:
    """Validate and persist test cases using stable UTF-8 formatting."""

    if not isinstance(cases, list) or not cases:
        raise ValueError("Bộ test phải là một danh sách không rỗng.")
    seen_ids: set[int] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Test #{index} phải là object.")
        case_id = int(case.get("id", index))
        if case_id in seen_ids:
            raise ValueError(f"ID test bị trùng: {case_id}.")
        seen_ids.add(case_id)
        if not str(case.get("question", "")).strip():
            raise ValueError(f"Test #{case_id} chưa có câu hỏi.")
        if not str(case.get("expected_behavior", "")).strip():
            raise ValueError(f"Test #{case_id} chưa có expected_behavior.")
        case["id"] = case_id
        checks = case.get("checks", {})
        if checks and not isinstance(checks, dict):
            raise ValueError(f"checks của test #{case_id} phải là object.")
    CONFIG_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tool_actions(trace: list[dict[str, Any]]) -> list[str]:
    return [str(event["action"]) for event in trace if event.get("action")]


def score_agent_result(case: dict[str, Any], result: Any) -> dict[str, Any]:
    """Score a result objectively from machine-readable expectations (0–2 each)."""

    checks = case.get("checks") if isinstance(case.get("checks"), dict) else {}
    actions = _tool_actions(result.trace)
    answer_folded = result.final_answer.casefold()
    allowed_stops = checks.get("stop_reasons", [])
    contains = checks.get("answer_contains", [])
    recommendation_count = checks.get("recommendation_count")
    recommendations = result.data.get("recommendations", []) if isinstance(result.data, dict) else []

    factual_checks = []
    if allowed_stops:
        factual_checks.append(result.stop_reason in allowed_stops)
    if contains:
        factual_checks.append(all(str(term).casefold() in answer_folded for term in contains))
    if recommendation_count is not None:
        factual_checks.append(len(recommendations) == int(recommendation_count))
    factual = 2 if factual_checks and all(factual_checks) else 1 if result.success else 0

    required_tools = set(checks.get("required_tools", []))
    forbidden_tools = set(checks.get("forbidden_tools", []))
    action_set = set(actions)
    tool_ok = required_tools.issubset(action_set) and forbidden_tools.isdisjoint(action_set)
    max_tools = checks.get("max_tools")
    if max_tools is not None:
        tool_ok = tool_ok and len(actions) <= int(max_tools)
    tool_selection = 2 if tool_ok else 1 if required_tools.intersection(action_set) else 0

    tool_events = [event for event in result.trace if event.get("action")]
    if required_tools:
        grounded = 2 if tool_events and all(event.get("tool_success") is not False and event.get("observation") is not None for event in tool_events) else 1
    else:
        grounded = 2 if result.stop_reason in {"out_of_scope", "prompt_injection", "suitability_answer", "knowledge_answer"} else 1

    bad_stops = {"max_iterations", "repeated_action", "backend_error", "provider_timeout"}
    max_steps = int(checks.get("max_steps", 20))
    termination = 2 if result.stop_reason not in bad_stops and result.steps <= max_steps else 0
    scores = {
        "factual_correctness": factual,
        "grounding": grounded,
        "tool_selection": tool_selection,
        "termination": termination,
    }
    total = sum(scores.values())
    return {**scores, "total": total, "max_total": 8, "passed": total >= 7}


def run_unit_tests() -> dict[str, Any]:
    """Run the repository's unittest suite with the active interpreter."""

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return {"success": completed.returncode == 0, "returncode": completed.returncode, "output": output}


def audit_submission_files() -> list[dict[str, Any]]:
    """Check mandatory artifacts and basic repository hygiene."""

    checks = [
        {"item": path, "passed": (PROJECT_ROOT / path).is_file(), "detail": "Có file" if (PROJECT_ROOT / path).is_file() else "Thiếu file"}
        for path in REQUIRED_ARTIFACTS
    ]
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    ).stdout.splitlines()
    checks.extend([
        {"item": ".env không bị Git track", "passed": ".env" not in tracked, "detail": "An toàn" if ".env" not in tracked else "Cần git rm --cached .env"},
        {"item": "Không track __pycache__", "passed": not any("__pycache__" in path for path in tracked), "detail": "Sạch"},
        {"item": "Tool registry có docstring", "passed": all(getattr(tool, "__doc__", None) for tool in AVAILABLE_TOOLS.values()), "detail": f"{len(AVAILABLE_TOOLS)} tools"},
    ])
    return checks


def _evaluate_case(case: dict[str, Any], provider: Any) -> dict[str, Any]:
    baseline_answer = run_baseline_chatbot(case["question"], provider, verbose=False)
    session = GiftAssistantSession(provider)
    for setup_turn in case.get("setup_turns", []):
        session.chat(str(setup_turn), verbose=False)
    result = session.chat(case["question"], verbose=False)
    return {
        "id": case["id"],
        "category": case.get("category", ""),
        "question": case["question"],
        "expected_behavior": case.get("expected_behavior", ""),
        "evaluated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline": {"answer": baseline_answer, "tool_calls": 0},
        "result": result.to_dict(),
        "actions": _tool_actions(result.trace),
        "score": score_agent_result(case, result),
    }


def run_evaluation_suite(
    provider_name: str = "mock",
    *,
    write_artifacts: bool = True,
    case_ids: list[int] | None = None,
    merge_existing: bool = False,
) -> dict[str, Any]:
    """Run all/selected cases, score traces and optionally merge into the current report."""

    tests = load_test_cases(str(CONFIG_PATH))
    selected_ids = {int(item) for item in case_ids} if case_ids else None
    selected_tests = [case for case in tests if selected_ids is None or int(case["id"]) in selected_ids]
    if not selected_tests:
        raise ValueError("Không tìm thấy test case cần chạy.")
    provider = get_llm_provider(provider_name)
    fresh_results = [_evaluate_case(case, provider) for case in selected_tests]
    case_results = fresh_results
    if merge_existing and TRACE_JSON_PATH.exists():
        try:
            existing = json.loads(TRACE_JSON_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if existing.get("provider") == provider_name and isinstance(existing.get("cases"), list):
            merged = {int(item["id"]): item for item in existing["cases"]}
            merged.update({int(item["id"]): item for item in fresh_results})
            case_results = [merged[key] for key in sorted(merged)]
    unit_tests = run_unit_tests()
    artifact_checks = audit_submission_files()
    passed_cases = sum(item["score"]["passed"] for item in case_results)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": provider_name,
        "summary": {
            "case_count": len(case_results),
            "passed_cases": passed_cases,
            "average_score": round(sum(item["score"]["total"] for item in case_results) / max(len(case_results), 1), 2),
            "unit_tests_passed": unit_tests["success"],
            "artifacts_passed": sum(item["passed"] for item in artifact_checks),
            "artifacts_total": len(artifact_checks),
        },
        "cases": case_results,
        "unit_tests": unit_tests,
        "artifact_checks": artifact_checks,
    }
    if write_artifacts:
        write_evaluation_artifacts(report)
    return report


def _evaluation_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = []
    for item in report["cases"]:
        score = item["score"]
        actions = " → ".join(item["actions"]) or "0 tool"
        rows.append(
            f"| {item['id']} | {item['category']} | `{item['result']['stop_reason']}` | {actions} | "
            f"{score['factual_correctness']} | {score['grounding']} | {score['tool_selection']} | "
            f"{score['termination']} | **{score['total']}/8** | {'PASS' if score['passed'] else 'REVIEW'} |"
        )
    return "\n".join([
        GENERATED_START,
        "## Kết quả đánh giá tự động gần nhất",
        "",
        f"- Thời gian: `{report['generated_at']}`",
        f"- Provider: `{report['provider']}`",
        f"- Test cases đạt: **{summary['passed_cases']}/{summary['case_count']}**",
        f"- Điểm trung bình: **{summary['average_score']}/8**",
        f"- Unit tests: **{'PASS' if summary['unit_tests_passed'] else 'FAIL'}**",
        f"- Artifact checklist: **{summary['artifacts_passed']}/{summary['artifacts_total']}**",
        "",
        "| ID | Loại | Stop reason | Tool path | Fact | Ground | Tool | Stop | Tổng | Kết quả |",
        "| ---: | --- | --- | --- | :---: | :---: | :---: | :---: | :---: | --- |",
        *rows,
        "",
        "> Điểm tự động là bằng chứng kỹ thuật có thể tái lập; phần nhận xét chất lượng ngôn ngữ và cross-audit vẫn cần người chấm xác nhận.",
        GENERATED_END,
    ])


def write_evaluation_artifacts(report: dict[str, Any]) -> None:
    """Write reproducible traces, generated report section and submission checks."""

    TRACE_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    existing = TRACE_REPORT_PATH.read_text(encoding="utf-8") if TRACE_REPORT_PATH.exists() else "# Trace Evaluation\n"
    generated = _evaluation_markdown(report)
    if GENERATED_START in existing and GENERATED_END in existing:
        before = existing.split(GENERATED_START, 1)[0].rstrip()
        after = existing.split(GENERATED_END, 1)[1].lstrip()
        updated = f"{before}\n\n{generated}\n\n{after}".rstrip() + "\n"
    else:
        updated = existing.rstrip() + "\n\n" + generated + "\n"
    TRACE_REPORT_PATH.write_text(updated, encoding="utf-8")

    checklist_lines = [
        "# Submission Checklist (tự động)", "", f"Cập nhật: `{report['generated_at']}`", "",
    ]
    checklist_lines.extend(
        f"- [{'x' if item['passed'] else ' '}] {item['item']} — {item.get('detail', '')}"
        for item in report["artifact_checks"]
    )
    checklist_lines.extend([
        "", f"- [{'x' if report['unit_tests']['success'] else ' '}] Unit tests chạy thành công",
        f"- [{'x' if report['summary']['passed_cases'] == report['summary']['case_count'] else ' '}] Toàn bộ test cases đạt ngưỡng tự động",
        "- [ ] Điền tên nhóm/người chấm chéo và phản hồi thật trong docs/cross_audit.md",
        "- [ ] Kiểm tra `git status`, commit và push đúng nhánh nộp bài",
    ])
    CHECKLIST_PATH.write_text("\n".join(checklist_lines) + "\n", encoding="utf-8")

    if not CROSS_AUDIT_PATH.exists():
        CROSS_AUDIT_PATH.write_text(
            "# Biên bản Cross-Audit\n\n"
            "- Nhóm/người chấm chéo: _Chưa điền_\n"
            "- Thời gian: _Chưa điền_\n"
            "- Commit được kiểm tra: _Chưa điền_\n\n"
            "## Attack cases nội bộ đã chạy\n\n"
            "1. Prompt injection giả admin/API key.\n"
            "2. Xung đột accessibility: đèn đọc sách cho người mù.\n"
            "3. Dữ liệu ngân sách âm/mơ hồ.\n"
            "4. Tool lặp, unknown tool và malformed arguments.\n\n"
            "## Phản hồi của nhóm chấm chéo\n\n_Chưa có — cần người chấm thật điền vào trước khi nộp._\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy rubric evaluator và sinh artifact nộp bài.")
    parser.add_argument("--provider", default="mock", choices=("mock", "openai", "gemini", "anthropic", "openrouter"))
    parser.add_argument("--no-write", action="store_true", help="Chỉ chạy, không cập nhật docs.")
    parser.add_argument("--case", type=int, action="append", dest="case_ids", help="Chỉ chạy ID này; có thể lặp lại.")
    parser.add_argument("--merge", action="store_true", help="Hợp nhất case được chạy lại vào report hiện tại cùng provider.")
    args = parser.parse_args()
    report = run_evaluation_suite(
        args.provider,
        write_artifacts=not args.no_write,
        case_ids=args.case_ids,
        merge_existing=args.merge,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
