# Báo cáo giám sát và đánh giá GiftSense Agent

## 1. Agentic Fit

| Tiêu chí | Điểm | Lý do |
| --- | :---: | --- |
| Multi-step Reasoning | 5/5 | Phải thu thập hồ sơ, đánh giá thiếu dữ liệu, tìm, lọc và xếp hạng. |
| Tool Interaction | 5/5 | Kết quả Top 3 chỉ lấy từ catalog và các Observation deterministic. |
| Dynamic Decision | 5/5 | Thiếu dữ liệu thì hỏi; đủ dữ liệu mới tìm; phản hồi sẽ cập nhật hồ sơ và xếp hạng lại. |
| Long Horizon | 4/5 | Hỗ trợ hội thoại nhiều lượt và lưu hồ sơ trong session. |
| **Tổng** | **19/20** | **Bài toán phù hợp với Agent.** |

## 2. Kiến trúc quan sát

Mỗi lượt Agent trả về một `AgentResult` gồm:

- `success`, `stop_reason`, `steps`.
- `final_answer`.
- `trace`: danh sách `Thought → Action → Action Input → Observation`.
- `data`: hồ sơ tích lũy và danh sách đề xuất grounded.

Giao diện Streamlit cho phép mở phần **Trace Thought → Action → Observation** để xem trực tiếp.

## 3. Trace thành công — đủ thông tin tối thiểu

**Input:** “Tìm quà cho bạn nữ hướng nội, ngân sách tối đa 500.000 đồng.”

Trace nghiệm thu với OpenAI Provider:

```text
classify_gift_scope
→ extract_recipient_profile
→ assess_profile
→ search_gift_catalog
→ check_gift_constraints
→ rank_and_diversify_gifts
→ Final Answer: Top 3 grounded
```

Kết quả:

- Không hỏi lại ba trường đã có.
- LLM tự chọn tool từ registry động.
- Không có parse error hoặc tool error.
- Trả đúng ba món, tất cả không vượt 500.000 đồng.
- Mỗi món có giá tham khảo, điểm, ý nghĩa, lý do và lưu ý.

## 4. Trace thiếu thông tin

**Input lượt 1:** “Tìm quà cho bạn nữ.”

```text
classify_gift_scope
→ extract_recipient_profile
→ assess_profile
→ need_more_information
```

Agent hỏi đúng `personality` và `budget_max`, chưa gọi tool tìm quà.

**Input lượt 2:** “Bạn ấy hướng nội và ngân sách 500k.”

Hồ sơ cũ được hợp nhất với dữ liệu mới; Agent bắt đầu tìm/lọc/xếp hạng và trả Top 3.

## 5. Failed Trace và Root Cause Analysis

| Phiên bản | Biểu hiện | Root cause | Agent V2 recovery |
| --- | --- | --- | --- |
| Trước tích hợp | Prompt gọi `analyze_personality`, `search_gift_catalog`, `check_gift_stock` nhưng registry chỉ có `check_infor`, `ask_infor`, `recommend_gift`. | Contract giữa Role 2 và Role 3 không đồng nhất. | App sinh tool description trực tiếp từ `AVAILABLE_TOOLS`; unknown tool trả Observation liệt kê tool hợp lệ. |
| Trước tích hợp | Tool bắt buộc đủ sáu trường nhưng không nhận ngân sách; trả bốn món. | Điều kiện đầu vào/đầu ra lệch đặc tả. | Chuẩn hóa ba trường tối thiểu, trường bổ sung là optional, Top 3 cố định. |
| Repeated Action | LLM có thể gọi lại cùng tool và cùng input. | Model không nhận ra đang bị kẹt. | App phát hiện action key trùng và dừng với `repeated_action`; Hybrid Agent chuyển sang grounded fallback. |
| Malformed Args | LLM thiếu hoặc sai tên tham số. | Output không khớp signature Python. | `inspect.signature().bind()` trả Observation lỗi, không làm ứng dụng crash. |

## 6. Kết quả kiểm thử

- `19/19` unit/integration tests pass ở chế độ offline mock, gồm authoritative tool inputs, suitability/accessibility, ngân sách mơ hồ, recovery provider, guardrails và tìm ảnh web.
- OpenAI `gpt-4o-mini` tự chọn đúng `evaluate_gift_suitability` cho câu hỏi về người khiếm thị, không dùng fallback.
- `7/7` test cases chạy hết, không crash.
- Streamlit render thành công, thao tác prompt mẫu tạo đủ hai chat messages.
- HTTP smoke test của UI trả `200`.
- OpenAI `gpt-4o-mini` vượt test đủ thông tin bằng grounded ReAct, không lỗi parser/tool.

## 7. Rubric tự đánh giá

| Tiêu chí | Điểm |
| --- | :---: |
| Hiểu đúng yêu cầu | 20/20 |
| Hỏi bổ sung hợp lý | 15/15 |
| Gọi đúng tool | 20/20 |
| Tuân thủ ngân sách/ràng buộc | 15/15 |
| Top 3 phù hợp và đa dạng | 18/20 |
| Giải thích rõ ràng | 10/10 |
| **Tổng** | **98/100** |
