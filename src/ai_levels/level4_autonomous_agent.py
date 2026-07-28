"""GiftSense Level-4 demo: model planning, ReAct execution and session memory.

Run from the repository root:
    python src/ai_levels/level4_autonomous_agent.py

Use LLM_PROVIDER=openai/gemini/anthropic/openrouter for autonomous planning.
Mock mode intentionally demonstrates the deterministic recovery path.
"""

from __future__ import annotations

import os
import sys


SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app import GiftAssistantSession
from providers import get_llm_provider


def run_demo() -> None:
    session = GiftAssistantSession(get_llm_provider())
    turns = [
        "Tặng đèn đọc sách cho một bạn nữ nhân dịp sinh nhật có được không?",
        "Nếu muốn Top 3 thì bạn ấy hướng nội, thích đọc sách, ngân sách 500k.",
        "Bỏ sách vì bạn ấy đã có rồi, ưu tiên một món mang tính trải nghiệm.",
    ]
    for index, message in enumerate(turns, start=1):
        result = session.chat(message, verbose=False)
        print(f"\n=== Turn {index}: {message} ===")
        for event in result.trace:
            if event.get("event") == "autonomous_plan":
                print("PLAN:", event.get("plan"))
            elif event.get("action"):
                print("ACTION:", event["action"])
                print("OBSERVATION:", event.get("observation"))
        print("FINAL:", result.final_answer)
        print("MEMORY PROFILE:", session.profile)


if __name__ == "__main__":
    run_demo()
