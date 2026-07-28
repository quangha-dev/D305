"""Cấp 3 — GiftSense ReAct demo: Thought → Action → Observation thật."""

from __future__ import annotations

import os
import sys


SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app import format_top3_result, run_react_agent
from providers import BaseLLMProvider
from tools import AVAILABLE_TOOLS


class ScriptedReActProvider(BaseLLMProvider):
    """Deterministic model script that demonstrates the real generic executor."""

    def __init__(self) -> None:
        self.responses = iter([
            'Thought: Cần trích hồ sơ từ yêu cầu.\nAction: extract_recipient_profile\nAction Input: {}',
            'Thought: Hồ sơ đã đủ; cần tìm catalog.\nAction: search_gift_catalog\nAction Input: {}',
            'Thought: Cần áp dụng ngân sách và loại trừ.\nAction: check_gift_constraints\nAction Input: {}',
            'Thought: Cần xếp hạng và đa dạng hóa Top 3.\nAction: rank_and_diversify_gifts\nAction Input: {}',
        ])

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return next(self.responses)


if __name__ == "__main__":
    query = "Tìm Top 3 quà cho bạn nữ hướng nội, ngân sách 500k."
    result = run_react_agent(
        query,
        ScriptedReActProvider(),
        tool_registry=AVAILABLE_TOOLS,
        authoritative_profile={},
        agent_plan={"intent": "recommendation"},
        manage_gift_state=True,
        verbose=True,
    )
    ranking = next(
        event["observation_data"]
        for event in reversed(result.trace)
        if event.get("action") == "rank_and_diversify_gifts"
    )
    print("\n=== FINAL GROUNDED TOP 3 ===")
    print(format_top3_result(ranking))
