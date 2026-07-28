"""Core application for the chatbot baseline and the ReAct agent.

Role 4 owns this integration layer.  Business rules stay in ``tools.py`` and
prompt/guardrail rules stay in ``prompts.py``.  The application only loads test
data, calls the provider, parses tool requests, executes registered tools and
records an observable trace.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass, field
import inspect
import json
import os
import re
import sys
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

# Allow ``python src/app.py`` to import modules next to this file on every OS.
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS, REACT_SYSTEM_PROMPT
from providers import BaseLLMProvider, get_llm_provider
from tools import AVAILABLE_TOOLS

try:
    from prompts import TIMEOUT_SECONDS
except ImportError:
    TIMEOUT_SECONDS = 10


load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


SAFE_FALLBACK = (
    "Xin lỗi, tôi chưa thể hoàn tất yêu cầu một cách đáng tin cậy. "
    "Vui lòng bổ sung thông tin hoặc thử lại sau."
)

GIFT_TOOL_NAMES = {
    "build_recipient_profile",
    "search_gift_catalog",
    "check_gift_constraints",
    "rank_and_diversify_gifts",
    "update_profile_from_feedback",
}


@dataclass
class ParsedResponse:
    """A normalized response produced by the LLM."""

    raw: str
    thought: str = ""
    action: str | None = None
    action_input: Any = None
    final_answer: str | None = None
    parse_error: str | None = None


@dataclass
class ToolExecution:
    """Result of one protected tool execution."""

    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None

    @property
    def observation(self) -> str:
        value = self.output if self.error is None else {"success": False, "error": self.error}
        return to_json(value)


@dataclass
class AgentResult:
    """Stable return type used by the CLI and the test runner."""

    success: bool
    final_answer: str
    stop_reason: str
    steps: int = 0
    trace: list[dict[str, Any]] = field(default_factory=list)
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def to_json(value: Any) -> str:
    """Serialize observations without failing on custom return values."""

    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def load_test_cases(path: str | None = None) -> list[dict[str, Any]]:
    """Load and minimally validate Role 1's JSON test cases."""

    config_path = path or os.path.join(PROJECT_ROOT, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as file:
        tests = json.load(file)

    if not isinstance(tests, list):
        raise ValueError("test_cases.json phải chứa một JSON array.")

    normalized: list[dict[str, Any]] = []
    for index, test in enumerate(tests, start=1):
        if not isinstance(test, dict):
            raise ValueError(f"Test case #{index} phải là một JSON object.")
        question = test.get("question") or test.get("input") or test.get("user_input")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Test case #{index} thiếu trường question/input hợp lệ.")
        item = dict(test)
        item.setdefault("id", index)
        item["question"] = question.strip()
        normalized.append(item)
    return normalized


def describe_tools(tool_registry: Mapping[str, Any]) -> str:
    """Build a current tool list from the registry instead of hard-coding it."""

    descriptions: list[str] = []
    for name, tool in tool_registry.items():
        if not callable(tool):
            descriptions.append(f"- {name}: tool chưa phải callable")
            continue
        try:
            signature = str(inspect.signature(tool))
        except (TypeError, ValueError):
            signature = "(...)"
        doc = inspect.getdoc(tool) or "Không có mô tả."
        summary = doc.splitlines()[0].strip()
        descriptions.append(f"- {name}{signature}: {summary}")
    return "\n".join(descriptions) or "- Không có tool nào được đăng ký."


def _literal_or_text(raw_value: str) -> Any:
    """Parse JSON/Python literals safely and fall back to a plain string."""

    value = raw_value.strip()
    if not value:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
    return value.strip("` \t\r\n")


def _parse_compact_action(expression: str) -> tuple[str, Any] | None:
    """Parse formats such as ``get_weather['Hà Nội']`` without eval()."""

    expression = expression.strip().rstrip(".")
    try:
        node = ast.parse(expression, mode="eval").body
    except SyntaxError:
        return None

    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        slice_node = node.slice
        try:
            if isinstance(slice_node, ast.Tuple):
                values = [ast.literal_eval(element) for element in slice_node.elts]
            else:
                values = [ast.literal_eval(slice_node)]
        except (ValueError, TypeError):
            return None
        return node.value.id, values

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        try:
            args = [ast.literal_eval(argument) for argument in node.args]
            kwargs = {item.arg: ast.literal_eval(item.value) for item in node.keywords if item.arg}
        except (ValueError, TypeError):
            return None
        if kwargs and args:
            return node.func.id, {"__args__": args, "__kwargs__": kwargs}
        return node.func.id, kwargs or args
    return None


def parse_react_response(response: str) -> ParsedResponse:
    """Parse both the documented ReAct format and the old compact format."""

    raw = (response or "").strip()
    parsed = ParsedResponse(raw=raw)
    if not raw:
        parsed.parse_error = "LLM trả về nội dung rỗng."
        return parsed

    thought_match = re.search(
        r"(?ims)^\s*Thought\s*:\s*(.*?)(?=^\s*(?:Action|Final Answer)\s*:|\Z)",
        raw,
    )
    if thought_match:
        parsed.thought = thought_match.group(1).strip()

    final_match = re.search(r"(?ims)^\s*Final Answer\s*:\s*(.+)\Z", raw)
    if final_match:
        parsed.final_answer = final_match.group(1).strip()
        return parsed

    action_match = re.search(r"(?im)^\s*Action\s*:\s*(.+?)\s*$", raw)
    if action_match:
        action_text = action_match.group(1).strip().strip("`")
        compact = _parse_compact_action(action_text)
        if compact:
            parsed.action, parsed.action_input = compact
            return parsed

        name_match = re.match(r"^([A-Za-z_]\w*)$", action_text)
        if not name_match:
            parsed.parse_error = f"Action không hợp lệ: {action_text}"
            return parsed

        parsed.action = name_match.group(1)
        input_match = re.search(r"(?ims)^\s*Action Input\s*:\s*(.+)\Z", raw)
        parsed.action_input = _literal_or_text(input_match.group(1)) if input_match else {}
        return parsed

    # A direct answer is valid for a simple question that needs no tool.
    if not re.search(r"(?im)^\s*(?:Thought|Action|Observation)\s*:", raw):
        parsed.final_answer = raw
    else:
        parsed.parse_error = "Thiếu Action hoặc Final Answer đúng định dạng."
    return parsed


def _prepare_call_arguments(tool: Any, action_input: Any) -> tuple[list[Any], dict[str, Any]]:
    if isinstance(action_input, dict) and "__args__" in action_input:
        args = list(action_input.get("__args__") or [])
        kwargs = dict(action_input.get("__kwargs__") or {})
    elif isinstance(action_input, dict):
        args, kwargs = [], action_input
    elif isinstance(action_input, (list, tuple)):
        args, kwargs = list(action_input), {}
    elif action_input in (None, ""):
        args, kwargs = [], {}
    else:
        args, kwargs = [action_input], {}

    # bind() catches missing, surplus and misspelled parameters before execution.
    inspect.signature(tool).bind(*args, **kwargs)
    return args, kwargs


def execute_tool(
    tool_name: str,
    action_input: Any,
    tool_registry: Mapping[str, Any] | None = None,
    timeout_seconds: int | float = TIMEOUT_SECONDS,
) -> ToolExecution:
    """Validate and execute a registered tool with timeout and error isolation."""

    registry = tool_registry if tool_registry is not None else AVAILABLE_TOOLS
    tool = registry.get(tool_name)
    if tool is None or not callable(tool):
        valid_names = ", ".join(sorted(registry)) or "(không có)"
        return ToolExecution(
            tool_name=tool_name,
            success=False,
            error=f"Tool '{tool_name}' không tồn tại. Tool hợp lệ: {valid_names}.",
        )

    try:
        args, kwargs = _prepare_call_arguments(tool, action_input)
    except (TypeError, ValueError) as error:
        return ToolExecution(
            tool_name=tool_name,
            success=False,
            error=f"Tham số không hợp lệ cho {tool_name}{inspect.signature(tool)}: {error}",
        )

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{tool_name}")
    future = executor.submit(tool, *args, **kwargs)
    try:
        output = future.result(timeout=max(float(timeout_seconds), 0.1))
    except FutureTimeoutError:
        future.cancel()
        return ToolExecution(
            tool_name=tool_name,
            success=False,
            error=f"Tool '{tool_name}' vượt quá timeout {timeout_seconds} giây.",
        )
    except Exception as error:  # A tool failure must not crash the application.
        return ToolExecution(
            tool_name=tool_name,
            success=False,
            error=f"Tool '{tool_name}' gặp lỗi: {type(error).__name__}: {error}",
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    business_success = not (
        isinstance(output, dict) and output.get("success") is False
    )
    if isinstance(output, str) and output.strip().upper().startswith(("LỖI", "ERROR")):
        business_success = False
    return ToolExecution(tool_name=tool_name, success=business_success, output=output)


def run_baseline_chatbot(
    user_query: str,
    provider: BaseLLMProvider,
    *,
    verbose: bool = True,
) -> str:
    """Run exactly one LLM call without exposing any tool to the baseline."""

    if verbose:
        print(f"\n💬 [CHATBOT BASELINE] {user_query}")
    try:
        response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    except Exception as error:
        response = f"Không thể gọi LLM provider: {type(error).__name__}: {error}"
    if verbose:
        print(f"🤖 {response}")
    return response


def _build_iteration_prompt(
    user_query: str,
    history: Sequence[str],
    tool_registry: Mapping[str, Any],
) -> str:
    trace = "\n\n".join(history) if history else "(chưa có bước nào)"
    return (
        f"Yêu cầu ban đầu của người dùng:\n{user_query}\n\n"
        f"Tool registry hiện tại:\n{describe_tools(tool_registry)}\n\n"
        f"Trace đã có:\n{trace}\n\n"
        "Hãy đưa ra đúng một bước tiếp theo. Nếu gọi tool, dùng Action và Action Input. "
        "Nếu đã đủ dữ liệu, trả Final Answer. Không tự tạo Observation."
    )


def run_react_agent(
    user_query: str,
    provider: BaseLLMProvider,
    *,
    tool_registry: Mapping[str, Any] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    timeout_seconds: int | float = TIMEOUT_SECONDS,
    verbose: bool = True,
) -> AgentResult:
    """Run a provider-driven Thought -> Action -> Observation loop safely."""

    registry = tool_registry if tool_registry is not None else AVAILABLE_TOOLS
    history: list[str] = []
    trace: list[dict[str, Any]] = []
    seen_actions: set[str] = set()

    if verbose:
        print(f"\n🤖 [REACT AGENT] {user_query}")

    for step in range(1, max(int(max_iterations), 1) + 1):
        iteration_prompt = _build_iteration_prompt(user_query, history, registry)
        try:
            raw_response = provider.generate(
                iteration_prompt,
                system_prompt=REACT_SYSTEM_PROMPT,
            )
        except Exception as error:
            message = f"Không thể gọi LLM provider: {type(error).__name__}: {error}"
            trace.append({"step": step, "error": message})
            return AgentResult(False, SAFE_FALLBACK, "provider_error", step, trace)

        parsed = parse_react_response(raw_response)
        event: dict[str, Any] = {
            "step": step,
            "thought": parsed.thought,
            "raw_response": parsed.raw,
        }

        if verbose:
            print(f"\n--- Step {step}/{max_iterations} ---")
            if parsed.thought:
                print(f"🧠 Thought: {parsed.thought}")

        if parsed.final_answer:
            event["final_answer"] = parsed.final_answer
            trace.append(event)
            if verbose:
                print(f"🏁 Final Answer: {parsed.final_answer}")
            return AgentResult(True, parsed.final_answer, "final_answer", step, trace)

        if parsed.parse_error or not parsed.action:
            error = parsed.parse_error or "Không tìm thấy action."
            event["parse_error"] = error
            trace.append(event)
            history.extend([parsed.raw, f"Observation: LỖI FORMAT: {error}"])
            if verbose:
                print(f"⚠️ {error}")
            continue

        action_key = f"{parsed.action}:{to_json(parsed.action_input)}"
        event["action"] = parsed.action
        event["action_input"] = parsed.action_input
        if action_key in seen_actions:
            event["error"] = "Action và tham số bị lặp lại."
            trace.append(event)
            if verbose:
                print("🛡️ Guardrail: phát hiện action lặp lại.")
            return AgentResult(False, SAFE_FALLBACK, "repeated_action", step, trace)
        seen_actions.add(action_key)

        execution = execute_tool(
            parsed.action,
            parsed.action_input,
            registry,
            timeout_seconds,
        )
        event["tool_success"] = execution.success
        event["observation"] = execution.observation
        trace.append(event)
        history.extend(
            [
                parsed.raw,
                f"Observation: {execution.observation}",
            ]
        )
        if verbose:
            print(f"🛠️ Action: {parsed.action} {to_json(parsed.action_input)}")
            print(f"👁️ Observation: {execution.observation}")

    if verbose:
        print(f"🛡️ Guardrail: đã đạt MAX_ITERATIONS={max_iterations}.")
    return AgentResult(False, SAFE_FALLBACK, "max_iterations", max_iterations, trace)


def gift_tools_ready(tool_registry: Mapping[str, Any] | None = None) -> bool:
    """Return True after Role 2 has registered all five agreed gift tools."""

    registry = tool_registry if tool_registry is not None else AVAILABLE_TOOLS
    return GIFT_TOOL_NAMES.issubset(registry) and all(
        callable(registry[name]) for name in GIFT_TOOL_NAMES
    )


def _tool_output_or_error(execution: ToolExecution) -> Any:
    if execution.error:
        return {"success": False, "error": execution.error}
    return execution.output


def _extract_list(value: Any, keys: Sequence[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def format_top3_result(recommendations: Any) -> str:
    """Format common Role 2 result shapes into the required Vietnamese Top 3."""

    gifts = _extract_list(
        recommendations,
        ("recommendations", "top_gifts", "gifts", "results", "data", "accepted"),
    )[:3]
    if not gifts:
        return "Không tìm thấy đủ món quà phù hợp với các ràng buộc hiện tại."

    blocks: list[str] = []
    for index, gift in enumerate(gifts, start=1):
        if not isinstance(gift, dict):
            blocks.append(f"Top {index}: {gift}")
            continue
        rank = gift.get("rank", index)
        name = gift.get("name") or gift.get("gift_name") or gift.get("id", "Món quà")
        price = gift.get("price", gift.get("reference_price", "Chưa có dữ liệu"))
        score = gift.get("score", gift.get("match_score", "Chưa chấm"))
        reasons = gift.get("reasons") or gift.get("reason") or []
        cautions = gift.get("cautions") or gift.get("notes") or gift.get("note") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        if isinstance(cautions, str):
            cautions = [cautions]
        price_text = f"{price:,.0f} đồng" if isinstance(price, (int, float)) else str(price)
        score_text = f"{score}/100" if isinstance(score, (int, float)) else str(score)
        reason_text = "\n".join(f"- {item}" for item in reasons) or "- Phù hợp hồ sơ đã cung cấp."
        caution_text = "\n".join(f"- {item}" for item in cautions) or "- Kiểm tra thông tin sản phẩm trước khi mua."
        blocks.append(
            f"Top {rank}: {name}\n"
            f"Giá tham khảo: {price_text}\n"
            f"Mức độ phù hợp: {score_text}\n\n"
            f"Lý do:\n{reason_text}\n\n"
            f"Lưu ý:\n{caution_text}"
        )
    return "\n\n".join(blocks)


def _recommend_gifts_for_profile(
    profile: dict[str, Any],
    registry: Mapping[str, Any],
    trace: list[dict[str, Any]],
    *,
    verbose: bool,
) -> AgentResult:
    """Run search -> constraint check -> ranking for a prepared profile."""

    search_call = execute_tool("search_gift_catalog", {"profile": profile}, registry)
    candidates = _tool_output_or_error(search_call)
    trace.append({"action": "search_gift_catalog", "observation": candidates})
    if not search_call.success:
        return AgentResult(False, SAFE_FALLBACK, "search_error", len(trace), trace)

    candidate_list = _extract_list(candidates, ("candidates", "gifts", "results", "data"))
    check_call = execute_tool(
        "check_gift_constraints",
        {"candidates": candidate_list, "profile": profile},
        registry,
    )
    checked = _tool_output_or_error(check_call)
    trace.append({"action": "check_gift_constraints", "observation": checked})
    if not check_call.success:
        return AgentResult(False, SAFE_FALLBACK, "constraint_error", len(trace), trace)

    accepted = _extract_list(checked, ("accepted", "candidates", "gifts", "results", "data"))
    rank_call = execute_tool(
        "rank_and_diversify_gifts",
        {"profile": profile, "candidates": accepted, "top_k": 3},
        registry,
    )
    ranked = _tool_output_or_error(rank_call)
    trace.append({"action": "rank_and_diversify_gifts", "observation": ranked})
    if not rank_call.success:
        return AgentResult(False, SAFE_FALLBACK, "ranking_error", len(trace), trace)

    answer = format_top3_result(ranked)
    if verbose:
        print(f"\n🎁 [GIFT PIPELINE]\n{answer}")
    return AgentResult(
        True,
        answer,
        "completed",
        len(trace),
        trace,
        {"profile": profile, "recommendations": ranked},
    )


def run_gift_pipeline(
    user_query: str,
    *,
    tool_registry: Mapping[str, Any] | None = None,
    verbose: bool = True,
) -> AgentResult:
    """Run the deterministic gift workflow once Role 2's tools are available."""

    registry = tool_registry if tool_registry is not None else AVAILABLE_TOOLS
    if not gift_tools_ready(registry):
        missing = sorted(GIFT_TOOL_NAMES.difference(registry))
        answer = "Gift pipeline chưa sẵn sàng. Thiếu tool: " + ", ".join(missing)
        return AgentResult(False, answer, "missing_gift_tools")

    trace: list[dict[str, Any]] = []

    profile_call = execute_tool("build_recipient_profile", {"user_description": user_query}, registry)
    profile_result = _tool_output_or_error(profile_call)
    trace.append({"action": "build_recipient_profile", "observation": profile_result})
    if not profile_call.success or not isinstance(profile_result, dict):
        return AgentResult(False, SAFE_FALLBACK, "profile_error", 1, trace)

    if profile_result.get("status") == "need_more_information":
        questions = profile_result.get("suggested_questions") or []
        if isinstance(questions, str):
            questions = [questions]
        answer = "\n".join(f"- {question}" for question in questions)
        return AgentResult(True, answer or "Vui lòng bổ sung thông tin người nhận.", "need_more_information", 1, trace)

    profile = profile_result.get("profile", profile_result)
    return _recommend_gifts_for_profile(profile, registry, trace, verbose=verbose)


def rerun_gift_pipeline_from_feedback(
    current_profile: dict[str, Any],
    previous_recommendations: list[dict[str, Any]],
    feedback: str,
    *,
    tool_registry: Mapping[str, Any] | None = None,
    verbose: bool = True,
) -> AgentResult:
    """Update a recipient profile from feedback and produce a fresh Top 3."""

    registry = tool_registry if tool_registry is not None else AVAILABLE_TOOLS
    if not gift_tools_ready(registry):
        missing = sorted(GIFT_TOOL_NAMES.difference(registry))
        answer = "Gift pipeline chưa sẵn sàng. Thiếu tool: " + ", ".join(missing)
        return AgentResult(False, answer, "missing_gift_tools")

    trace: list[dict[str, Any]] = []
    update_call = execute_tool(
        "update_profile_from_feedback",
        {
            "current_profile": current_profile,
            "previous_recommendations": previous_recommendations,
            "feedback": feedback,
        },
        registry,
    )
    update_result = _tool_output_or_error(update_call)
    trace.append({"action": "update_profile_from_feedback", "observation": update_result})
    if not update_call.success or not isinstance(update_result, dict):
        return AgentResult(False, SAFE_FALLBACK, "feedback_update_error", 1, trace)

    profile_patch = update_result.get("profile", update_result)
    updated_profile = dict(current_profile)
    updated_profile.update(profile_patch)
    return _recommend_gifts_for_profile(updated_profile, registry, trace, verbose=verbose)


def run_all_test_cases(
    tests: Sequence[dict[str, Any]],
    provider: BaseLLMProvider,
    *,
    mode: str = "agent",
    tool_registry: Mapping[str, Any] | None = None,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Execute every selected test without pretending semantic REVIEW is PASS."""

    results: list[dict[str, Any]] = []
    for test in tests:
        question = test["question"]
        print(f"\n{'=' * 70}\nTEST #{test['id']}: {test.get('category', '')}\n{question}")
        if mode == "baseline":
            answer = run_baseline_chatbot(question, provider, verbose=verbose)
            item = {"id": test["id"], "status": "REVIEW", "answer": answer}
        elif mode == "pipeline":
            result = run_gift_pipeline(question, tool_registry=tool_registry, verbose=verbose)
            item = {"id": test["id"], "status": "REVIEW" if result.success else "ERROR", **result.to_dict()}
        else:
            result = run_react_agent(
                question,
                provider,
                tool_registry=tool_registry,
                verbose=verbose,
            )
            status = "REVIEW" if result.success else "SAFE_FALLBACK"
            item = {"id": test["id"], "status": status, **result.to_dict()}
        item["expected_behavior"] = test.get("expected_behavior") or test.get("expected")
        results.append(item)
        print(f"📌 Trạng thái: {item['status']} (cần đối chiếu expected_behavior)")
    return results


def _select_tests(tests: Sequence[dict[str, Any]], selector: str) -> list[dict[str, Any]]:
    if selector.lower() == "all":
        return list(tests)
    try:
        selected_id = int(selector)
    except ValueError as error:
        raise ValueError("--test phải là 'all' hoặc ID dạng số.") from error
    selected = [test for test in tests if int(test["id"]) == selected_id]
    if not selected:
        raise ValueError(f"Không tìm thấy test case ID={selected_id}.")
    return selected


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chatbot baseline và ReAct Agent runner")
    parser.add_argument(
        "--mode",
        choices=("agent", "baseline", "compare", "pipeline"),
        default="agent",
        help="Chế độ chạy (mặc định: agent).",
    )
    parser.add_argument("--test", default="all", help="ID test hoặc 'all'.")
    parser.add_argument("--query", help="Chạy trực tiếp một câu hỏi thay vì test_cases.json.")
    parser.add_argument("--quiet", action="store_true", help="Giảm log chi tiết.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print("=" * 70)
    print("🎁 TRỢ LÝ NẮM BẮT TÍNH CÁCH & CHỌN QUÀ TẶNG")
    print(f"🔌 Provider: {provider.__class__.__name__} | Model: {model_name}")
    print(f"🛠️ Tools: {', '.join(AVAILABLE_TOOLS) or '(chưa có)'}")
    print(f"🧩 Gift tools ready: {'Có' if gift_tools_ready() else 'Chưa'}")

    if args.query:
        tests = [{"id": 1, "question": args.query, "category": "CLI query"}]
    else:
        try:
            tests = _select_tests(load_test_cases(), args.test)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"❌ Không thể tải test case: {error}")
            return 2

    modes = ("baseline", "agent") if args.mode == "compare" else (args.mode,)
    for mode in modes:
        print(f"\n▶️ Chế độ: {mode.upper()}")
        run_all_test_cases(
            tests,
            provider,
            mode=mode,
            verbose=not args.quiet,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
