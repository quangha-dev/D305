"""Cấp 2 — GiftSense LLM baseline: một model call, không có tool grounding."""

from __future__ import annotations

import os
import sys


SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app import run_baseline_chatbot
from providers import BaseLLMProvider


class OfflineBaselineProvider(BaseLLMProvider):
    """Small deterministic provider so this educational demo needs no API key."""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            "Người hướng nội thường hợp quà riêng tư và có ý nghĩa như sách, sổ tay hoặc vật dụng thư giãn. "
            "Đây chỉ là tư vấn chung: chatbot baseline không có catalog, giá hay Observation để kiểm chứng."
        )


if __name__ == "__main__":
    question = "Người hướng nội thường hợp phong cách quà nào?"
    print("=== GIFT SENSE · LEVEL 2 LLM BASELINE ===")
    print(run_baseline_chatbot(question, OfflineBaselineProvider(), verbose=False))
    print("Tool calls: 0")
