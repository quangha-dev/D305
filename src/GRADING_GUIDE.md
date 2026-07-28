# Hướng dẫn chấm nhanh GiftSense

## Một lệnh nghiệm thu

Chạy từ thư mục gốc dự án, không cần API key:

```powershell
.\.venv\Scripts\python.exe src\grader_demo.py --provider mock
```

Exit code `0` nghĩa là toàn bộ kiểm tra kỹ thuật và test case đều đạt. Dùng
`--show-trace` để in trace ReAct mẫu, hoặc `--json` để máy chấm nhận toàn bộ kết
quả có cấu trúc. Dùng `--provider openai --write-artifacts` để kiểm tra đường đi
của model thật và cập nhật báo cáo trong `docs/`.

## Bản đồ rubric trong mã nguồn

| Rubric | Bằng chứng chính |
| --- | --- |
| Agentic Fit & Test Design | `evaluation.py`, `config/test_cases.json`, `RUBRIC_EVIDENCE` |
| ReAct & Tools | `app.py::run_react_agent`, `tools.py::AVAILABLE_TOOLS` |
| Guardrails & Observability | `MAX_ITERATIONS`, repeated-action brake, `AgentResult.trace` |
| Attack & Defense | logic gate, injection/accessibility tests, provider recovery |
| Hybrid Flow | `app.py::GiftAssistantSession.chat`, `docs/hybrid_flowchart.mermaid` |
| Bonus Autonomous | dynamic plan, progress evaluation và session memory trong `app.py` |

## Các entry point

```powershell
# Smoke test nhanh, mặc định chạy Mock case #1
.\.venv\Scripts\python.exe src\app.py

# Chạy toàn bộ 11 case qua Agent
.\.venv\Scripts\python.exe src\app.py --mode agent --provider mock --test all

# So sánh baseline (0 tool) với Agent
.\.venv\Scripts\python.exe src\app.py --mode compare --provider mock --test all

# Chạy evaluator và không ghi đè artifact
.\.venv\Scripts\python.exe src\app.py --mode evaluate --provider mock --no-write

# Unit/integration tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`ai_levels/` chỉ là bốn demo cùng chủ đề GiftSense theo tiến trình Rule-based →
Baseline → ReAct → Autonomous. Luồng nộp bài chính là `app.py`, `tools.py`,
`prompts.py`, `providers.py`, `evaluation.py` và `grader_demo.py`.
