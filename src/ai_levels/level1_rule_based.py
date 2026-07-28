"""Cấp 1 — GiftSense rule-based: minh họa giới hạn của luật từ khóa."""

from __future__ import annotations


def rule_based_gift_bot(user_input: str) -> str:
    """Return a canned gift response from a tiny keyword table; no LLM/tool."""

    text = user_input.casefold()
    if any(term in text for term in ("bỏ qua hướng dẫn", "api key", "system prompt", "admin")):
        return "Mình chỉ hỗ trợ tư vấn quà và không thể thay đổi quy tắc hệ thống."
    if "hướng nội" in text:
        return "Có thể cân nhắc sách hoặc một món dùng trong không gian riêng; bot luật chưa biết ngân sách."
    if "năng động" in text:
        return "Có thể cân nhắc bình giữ nhiệt hoặc phụ kiện thể thao; bot luật chưa kiểm tra catalog."
    if "quà" in text or "tặng" in text:
        return "Bạn hãy cho biết thêm tính cách và ngân sách."
    return "Câu hỏi không khớp tập luật tư vấn quà đã cài đặt."


if __name__ == "__main__":
    print("=== GIFT SENSE · LEVEL 1 RULE-BASED ===")
    for query in ("Quà cho người hướng nội", "Bạn nam năng động", "Giải phương trình"):
        print(f"User: {query}\nBot : {rule_based_gift_bot(query)}\n")
