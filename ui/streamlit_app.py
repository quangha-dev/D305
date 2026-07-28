"""Local Streamlit interface for quickly testing the gift assistant."""

from __future__ import annotations

import html
import os
import sys
from urllib.parse import quote

import requests
import streamlit as st


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app import AgentResult, GiftAssistantSession
from providers import get_llm_provider


IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 15
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@st.cache_data(ttl=3600, show_spinner=False)
def download_image_bytes(image_url: str, file_title: str = "") -> bytes:
    """Download a remote image server-side so the browser never depends on CORS."""
    candidate_urls: list[str] = []
    if file_title:
        filename = file_title.removeprefix("File:")
        candidate_urls.append(
            f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{quote(filename)}?width=480"
        )
    candidate_urls.append(image_url)
    headers = {
        "User-Agent": "Mozilla/5.0 GiftSense/1.0 (local educational app)",
        "Referer": "https://commons.wikimedia.org/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    last_error: Exception | None = None
    for candidate_url in dict.fromkeys(candidate_urls):
        try:
            response = requests.get(
                candidate_url,
                timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
                headers=headers,
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                raise ValueError(f"URL không trả về ảnh ({content_type or 'không rõ MIME'})")
            if not response.content:
                raise ValueError("Tệp ảnh rỗng")
            if len(response.content) > MAX_IMAGE_BYTES:
                raise ValueError("Tệp ảnh vượt quá giới hạn 8 MB")
            return response.content
        except (requests.RequestException, ValueError) as error:
            last_error = error
    raise ValueError(f"Không tải được ảnh: {last_error}")


def prepare_image_cards(images: list[dict]) -> tuple[list[dict], list[str]]:
    """Create UI-only image cards without adding binary data to the Agent trace."""
    prepared: list[dict] = []
    errors: list[str] = []
    for image_item in images:
        card = dict(image_item)
        try:
            card["display_bytes"] = download_image_bytes(
                str(card["image_url"]),
                str(card.get("file_title", "")),
            )
            prepared.append(card)
        except (requests.RequestException, KeyError, TypeError, ValueError) as error:
            errors.append(f"{card.get('gift_name', 'Ảnh')}: {error}")
    return prepared, errors


st.set_page_config(
    page_title="GiftSense Agent",
    page_icon="💙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --blue-700: #1d4ed8;
        --blue-600: #2563eb;
        --blue-100: #dbeafe;
        --blue-50: #eff6ff;
        --slate-950: #0f172a;
        --slate-600: #475569;
        --slate-200: #e2e8f0;
        --white: #ffffff;
    }
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: #f8fafc !important;
        color: var(--slate-950) !important;
    }
    [data-testid="stHeader"] {
        background: rgba(255, 255, 255, .96) !important;
        border-bottom: 1px solid var(--slate-200);
    }
    [data-testid="stToolbar"], [data-testid="stToolbar"] * {
        color: var(--slate-600) !important;
    }
    #MainMenu, .stDeployButton { visibility: hidden; }

    [data-testid="stSidebar"] {
        background: var(--blue-50) !important;
        border-right: 1px solid var(--blue-100);
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span {
        color: var(--slate-950) !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: var(--white) !important;
        border-color: #bfdbfe !important;
        color: var(--slate-950) !important;
    }
    [data-testid="stSidebar"] hr { border-color: #bfdbfe; }

    .main .block-container {
        max-width: 1180px;
        padding-top: 2.6rem;
        padding-bottom: 7rem;
    }
    .hero {
        padding: 2rem 2.2rem;
        border-radius: 20px;
        background: var(--blue-700);
        color: var(--white) !important;
        margin-bottom: 1.2rem;
        box-shadow: 0 14px 35px rgba(29, 78, 216, .14);
    }
    .hero h1 {
        margin: 0;
        color: var(--white) !important;
        font-size: 2.25rem;
        letter-spacing: -.04em;
    }
    .hero p {
        margin: .6rem 0 0;
        max-width: 760px;
        color: var(--blue-100) !important;
        line-height: 1.65;
    }
    .status-card {
        border: 1px solid var(--blue-100);
        border-radius: 14px;
        padding: .9rem 1rem;
        background: var(--white);
        margin-bottom: .8rem;
    }
    .status-label { color: var(--slate-600); font-size: .76rem; text-transform: uppercase; letter-spacing: .08em; }
    .status-value { color: var(--blue-700); font-weight: 700; margin-top: .2rem; }
    .trace-card {
        display: flex;
        gap: .85rem;
        align-items: flex-start;
        background: var(--white);
        border: 1px solid var(--blue-100);
        border-left: 4px solid var(--blue-600);
        border-radius: 14px;
        padding: .9rem 1rem;
        margin: .55rem 0 .35rem;
    }
    .trace-number {
        display: grid;
        place-items: center;
        flex: 0 0 1.8rem;
        height: 1.8rem;
        border-radius: 999px;
        background: var(--blue-100);
        color: var(--blue-700);
        font-weight: 700;
        font-size: .82rem;
    }
    .trace-title { color: var(--slate-950); font-weight: 700; line-height: 1.35; }
    .trace-description { color: var(--slate-600); margin-top: .2rem; line-height: 1.5; }
    .image-consent {
        background: var(--blue-50);
        border: 1px solid #bfdbfe;
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin: 1rem 0 .6rem;
        color: var(--slate-950);
    }

    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: var(--slate-950);
    }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        color: var(--slate-600) !important;
    }

    div[data-testid="stButton"] > button {
        min-height: 2.65rem;
        border-radius: 12px !important;
        border: 1px solid #93c5fd !important;
        background: var(--white) !important;
        color: var(--blue-700) !important;
        box-shadow: none !important;
    }
    div[data-testid="stButton"] > button p,
    div[data-testid="stButton"] > button span {
        color: var(--blue-700) !important;
        font-weight: 600 !important;
    }
    div[data-testid="stButton"] > button:hover {
        border-color: var(--blue-600) !important;
        background: var(--blue-50) !important;
        color: var(--blue-700) !important;
    }
    div[data-testid="stButton"] > button:focus {
        border-color: var(--blue-600) !important;
        box-shadow: 0 0 0 3px var(--blue-100) !important;
    }

    [data-testid="stChatMessage"] {
        border-radius: 16px;
        border: 1px solid var(--blue-100);
        background: var(--white) !important;
        color: var(--slate-950) !important;
    }
    [data-testid="stChatMessage"] * { color: var(--slate-950); }
    [data-testid="stChatInput"] {
        background: var(--white) !important;
        border: 1px solid #93c5fd !important;
        border-radius: 14px !important;
        box-shadow: 0 8px 24px rgba(37, 99, 235, .10) !important;
    }
    [data-testid="stChatInput"] textarea {
        background: var(--white) !important;
        color: var(--slate-950) !important;
        caret-color: var(--blue-600) !important;
    }
    [data-testid="stChatInput"] textarea::placeholder {
        color: #64748b !important;
        opacity: 1 !important;
    }
    [data-testid="stChatInput"] button {
        background: var(--blue-600) !important;
        color: var(--white) !important;
    }
    [data-testid="stChatInput"] button svg { fill: var(--white) !important; }

    [data-testid="stExpander"] {
        background: var(--white) !important;
        border: 1px solid var(--blue-100) !important;
    }
    [data-testid="stJson"] {
        background: var(--white) !important;
        color: var(--slate-950) !important;
    }
    [data-testid="stSpinner"] *, [data-testid="stAlert"] * {
        color: var(--slate-950) !important;
    }

    @media (max-width: 768px) {
        .main .block-container { padding-top: 1.4rem; }
        .hero { padding: 1.4rem; border-radius: 16px; }
        .hero h1 { font-size: 1.75rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def new_session(provider_name: str) -> GiftAssistantSession:
    return GiftAssistantSession(get_llm_provider(provider_name))


def reset_chat(provider_name: str) -> None:
    st.session_state.agent = new_session(provider_name)
    st.session_state.messages = []
    st.session_state.last_result = None
    st.session_state.gift_images = []
    st.session_state.image_errors = []
    st.session_state.image_declined = False


def friendly_trace(event: dict, number: int) -> tuple[str, str]:
    action = event.get("action")
    observation = event.get("observation")
    if not isinstance(observation, dict):
        observation = event.get("observation_data") if isinstance(event.get("observation_data"), dict) else {}
    mapping = {
        "classify_gift_scope": ("Kiểm tra yêu cầu", "Xác nhận câu hỏi thuộc phạm vi tư vấn tính cách và quà tặng."),
        "scope_router": ("Chọn cách xử lý", "Chuyển câu hỏi sang luồng phù hợp mà không gọi công cụ thừa."),
        "extract_recipient_profile": ("Đọc thông tin người nhận", "Ghi nhận giới tính, tính cách, ngân sách và các sở thích đã cung cấp."),
        "update_profile_from_feedback": ("Cập nhật theo phản hồi", "Bổ sung điều người nhận đã có, không thích hoặc mong muốn mới."),
        "assess_profile": ("Kiểm tra thông tin", "Xác định đã đủ dữ liệu tối thiểu hay cần hỏi thêm."),
        "search_gift_catalog": ("Tìm quà phù hợp", "Tìm các lựa chọn tiềm năng trong danh mục quà tặng."),
        "check_gift_constraints": ("Lọc điều kiện bắt buộc", "Loại món vượt ngân sách, không thích hoặc đã sở hữu."),
        "rank_and_diversify_gifts": ("Xếp hạng và đa dạng hóa", "Chấm điểm, tránh các món quá giống nhau và chọn Top 3."),
        "search_gift_images": ("Tìm ảnh minh họa trên web", "Tìm một ảnh liên quan cho mỗi món trong Top 3 sau khi người dùng đồng ý."),
        "evaluate_gift_suitability": ("Đánh giá độ phù hợp", "Kiểm tra khả năng sử dụng, khả năng tiếp cận và rủi ro trước khi khuyên tặng."),
    }
    if action in mapping:
        title, description = mapping[action]
        if action == "search_gift_catalog" and isinstance(observation.get("candidates"), list):
            description = f"Đã tìm thấy {len(observation['candidates'])} lựa chọn tiềm năng từ danh mục."
        elif action == "check_gift_constraints":
            accepted = len(observation.get("accepted", []))
            rejected = len(observation.get("rejected", []))
            description = f"Giữ lại {accepted} món hợp lệ và loại {rejected} món vi phạm điều kiện."
        elif action == "rank_and_diversify_gifts":
            count = observation.get("count") or len(observation.get("recommendations", []))
            description = f"Đã chấm điểm và chọn {count} món quà phù hợp nhất."
        elif action == "assess_profile" and observation.get("missing_fields"):
            description = "Còn thiếu: " + ", ".join(observation["missing_fields"]) + "."
        return title, description

    event_name = event.get("event")
    if event_name == "logic_precheck":
        if event.get("stopped_before_tools"):
            return (
                "Phát hiện xung đột trước khi dùng công cụ",
                "Yêu cầu chưa hợp lý hoặc chưa an toàn cho người nhận nên Agent dừng trước bước tìm và xếp hạng quà.",
            )
        return "Kiểm tra logic ban đầu", "Xác nhận yêu cầu hợp lý và an toàn trước khi cho phép Agent sử dụng công cụ."
    if event_name == "provider_error":
        return "Kết nối AI gặp gián đoạn", event.get("error", "Provider hiện không khả dụng.")
    if event_name in {"react_recovery", "offline_fallback"}:
        return "Chuyển sang chế độ dự phòng", "Dùng công cụ và catalog offline để vẫn trả kết quả có căn cứ."
    if event_name == "suitability_recovery":
        return "Tự phục hồi đánh giá", "Model chưa gọi đúng tool nên hệ thống dùng tool đánh giá trực tiếp."
    if event.get("parse_error"):
        return "Tự sửa định dạng", "Phản hồi AI chưa đúng cấu trúc; hệ thống yêu cầu thử lại an toàn."
    if event.get("error"):
        return "Bước xử lý gặp lỗi", "Hệ thống đã chặn lỗi và không để ứng dụng bị dừng."
    if event.get("final_answer"):
        return "Hoàn thiện câu trả lời", "Tổng hợp kết quả từ các dữ liệu đã được kiểm chứng."
    return f"Bước xử lý {number}", "Agent đang phân tích và lựa chọn hành động tiếp theo."


def render_trace_cards(trace: list[dict]) -> None:
    st.markdown("### Agent đã xử lý như thế nào?")
    st.caption("Phần tóm tắt dành cho người dùng phổ thông. Mở từng bước nếu bạn muốn xem dữ liệu kỹ thuật.")
    for number, event in enumerate(trace, start=1):
        title, description = friendly_trace(event, number)
        st.markdown(
            f'<div class="trace-card"><div class="trace-number">{number}</div>'
            f'<div><div class="trace-title">{html.escape(title)}</div>'
            f'<div class="trace-description">{html.escape(description)}</div></div></div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Xem chi tiết kỹ thuật · Bước {number}", expanded=False):
            st.json(event, expanded=False)


def submit_message(message: str) -> None:
    clean_message = message.strip()
    if not clean_message:
        return
    st.session_state.messages.append({"role": "user", "content": clean_message})
    with st.status("Đang xử lý yêu cầu...", expanded=True) as live_status:
        st.write("1. Kiểm tra phạm vi và độ an toàn của câu hỏi")
        st.write("2. Đọc hồ sơ người nhận và chọn công cụ phù hợp")
        try:
            result = st.session_state.agent.chat(clean_message, verbose=False)
            live_status.update(label="Đã xử lý xong", state="complete", expanded=False)
        except Exception as error:
            result = AgentResult(
                False,
                "Backend đang gặp sự cố tạm thời. Bạn hãy thử lại hoặc khởi động lại ứng dụng.",
                "backend_error",
                1,
                [{"event": "backend_error", "error": f"{type(error).__name__}: {error}"}],
            )
            live_status.update(label="Không thể hoàn tất", state="error", expanded=True)
    st.session_state.messages.append({"role": "assistant", "content": result.final_answer})
    if result.stop_reason == "images_found":
        image_data = result.data if isinstance(result.data, dict) else {}
        prepared_images, download_errors = prepare_image_cards(image_data.get("images", []))
        st.session_state.gift_images = prepared_images
        st.session_state.image_errors = [*image_data.get("errors", []), *download_errors]
        previous_result = st.session_state.get("last_result")
        if previous_result:
            previous_result.trace.extend(result.trace)
        else:
            st.session_state.last_result = result
    elif result.stop_reason == "images_declined":
        st.session_state.image_declined = True
    else:
        if result.stop_reason in {"completed", "grounded_react"}:
            st.session_state.gift_images = []
            st.session_state.image_errors = []
            st.session_state.image_declined = False
        st.session_state.last_result = result


def search_images_from_button() -> None:
    with st.status("Đang tìm ảnh minh họa trên web...", expanded=True) as image_status:
        try:
            result = st.session_state.agent.search_recommendation_images()
        except Exception as error:
            result = AgentResult(
                False,
                "Không thể kết nối dịch vụ tìm ảnh. Kết quả Top 3 vẫn được giữ nguyên.",
                "image_search_failed",
                1,
                [{"event": "image_search_error", "error": f"{type(error).__name__}: {error}"}],
            )
        image_status.update(
            label="Đã tìm ảnh" if result.success else "Chưa tìm được ảnh",
            state="complete" if result.success else "error",
            expanded=False,
        )
    st.session_state.messages.append({"role": "assistant", "content": result.final_answer})
    image_data = result.data if isinstance(result.data, dict) else {}
    prepared_images, download_errors = prepare_image_cards(image_data.get("images", []))
    st.session_state.gift_images = prepared_images
    st.session_state.image_errors = [*image_data.get("errors", []), *download_errors]
    previous_result = st.session_state.get("last_result")
    if previous_result:
        previous_result.trace.extend(result.trace)


with st.sidebar:
    st.markdown("## GiftSense")
    st.caption("Bảng điều khiển kiểm thử Agent")
    st.success("Backend đang hoạt động")
    provider_name = st.selectbox(
        "LLM Provider",
        ("mock", "gemini", "openai", "anthropic", "openrouter"),
        help="Mock chạy hoàn toàn offline; các provider khác đọc API key từ .env.",
    )
    if "provider_name" not in st.session_state:
        st.session_state.provider_name = provider_name
    if st.session_state.provider_name != provider_name:
        st.session_state.provider_name = provider_name
        reset_chat(provider_name)

    if "agent" not in st.session_state:
        reset_chat(provider_name)
    st.session_state.setdefault("gift_images", [])
    st.session_state.setdefault("image_errors", [])
    st.session_state.setdefault("image_declined", False)

    if st.button("↻ Bắt đầu hồ sơ mới", use_container_width=True):
        reset_chat(provider_name)
        st.rerun()

    st.markdown("---")
    st.markdown("### Hồ sơ đang tích lũy")
    profile = st.session_state.agent.profile
    if profile:
        st.json(profile, expanded=False)
    else:
        st.caption("Chưa có dữ liệu người nhận.")

    st.markdown("---")
    st.caption("Thông tin tối thiểu: giới tính/cách xưng hô · tính cách/phong cách · ngân sách")


st.markdown(
    """
    <section class="hero">
      <h1>Chọn quà bằng sự thấu hiểu.</h1>
      <p>Mô tả người nhận theo cách tự nhiên. Agent sẽ hỏi đúng phần còn thiếu, dùng công cụ để lọc ngân sách và trả ba món quà có căn cứ.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

left, middle, right = st.columns(3)
with left:
    st.markdown('<div class="status-card"><div class="status-label">Luồng 1</div><div class="status-value">Đủ dữ liệu → Top 3</div></div>', unsafe_allow_html=True)
with middle:
    st.markdown('<div class="status-card"><div class="status-label">Luồng 2</div><div class="status-value">Thiếu dữ liệu → Hỏi tiếp</div></div>', unsafe_allow_html=True)
with right:
    last_reason = getattr(st.session_state.get("last_result"), "stop_reason", "Sẵn sàng")
    status_labels = {
        "completed": "Đã có Top 3", "grounded_react": "Đã có Top 3", "need_more_information": "Cần thêm thông tin",
        "out_of_scope": "Đã chặn ngoài phạm vi", "backend_error": "Backend gặp lỗi", "greeting": "Sẵn sàng",
        "images_found": "Đã tìm ảnh", "image_search_failed": "Không tìm được ảnh",
        "suitability_answer": "Đã đánh giá món quà",
    }
    friendly_status = status_labels.get(last_reason, last_reason)
    st.markdown(f'<div class="status-card"><div class="status-label">Trạng thái</div><div class="status-value">{html.escape(friendly_status)}</div></div>', unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown("#### Thử nhanh")
    examples = (
        "Tìm quà sinh nhật cho bạn nữ hướng nội, thích đọc sách, ngân sách 500k.",
        "Tôi muốn tìm quà cho một người bạn nam.",
        "Tìm quà cho bạn thân nữ năng động, màu xanh, thân mật 4/5, ngân sách 700k.",
    )
    columns = st.columns(3)
    for column, example in zip(columns, examples):
        with column:
            if st.button(example, use_container_width=True):
                submit_message(example)
                st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ví dụ: Bạn nữ hướng nội, thích đọc sách, ngân sách 500k..."):
    submit_message(prompt)
    st.rerun()

if (
    st.session_state.agent.recommendations
    and getattr(st.session_state.get("last_result"), "stop_reason", "") in {"completed", "grounded_react"}
    and not st.session_state.gift_images
    and not st.session_state.image_declined
):
    st.markdown(
        '<div class="image-consent"><strong>Bạn có muốn xem ảnh minh họa của 3 món quà này không?</strong>'
        '<br><span>Ảnh được tìm trên web và chỉ dùng để hình dung sản phẩm.</span></div>',
        unsafe_allow_html=True,
    )
    image_yes_column, image_no_column, _ = st.columns((1, 1, 3))
    with image_yes_column:
        if st.button("Có, xem 3 ảnh", use_container_width=True, type="primary"):
            search_images_from_button()
            st.rerun()
    with image_no_column:
        if st.button("Không cần", use_container_width=True):
            st.session_state.image_declined = True
            st.rerun()

if st.session_state.gift_images and any(
    "display_bytes" not in image_item for image_item in st.session_state.gift_images
):
    upgraded_images, upgrade_errors = prepare_image_cards(st.session_state.gift_images)
    st.session_state.gift_images = upgraded_images
    st.session_state.image_errors = [*st.session_state.image_errors, *upgrade_errors]

if st.session_state.gift_images:
    st.markdown("### Ảnh minh họa Top 3")
    st.caption("Nguồn Wikimedia Commons · Ảnh có thể khác mẫu sản phẩm thực tế.")
    image_columns = st.columns(3)
    for column, image_item in zip(image_columns, st.session_state.gift_images):
        with column:
            st.image(
                image_item["display_bytes"],
                caption=image_item["gift_name"],
                width="stretch",
            )
            if image_item.get("source_url"):
                st.link_button(
                    f"Xem nguồn · {image_item.get('license', 'Commons')}",
                    image_item["source_url"],
                    use_container_width=True,
                )

if st.session_state.image_errors and not st.session_state.gift_images:
    st.warning("Không tìm thấy ảnh phù hợp hoặc kết nối dịch vụ ảnh đang gián đoạn. Top 3 vẫn được giữ nguyên.")

last_result = st.session_state.get("last_result")
if last_result:
    render_trace_cards(last_result.trace)
