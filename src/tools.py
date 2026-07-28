"""Deterministic tools for the gift recommendation agent.

Every tool returns JSON-compatible data and converts business failures into an
``error`` field instead of raising.  ``AVAILABLE_TOOLS`` is the only registry
the application needs, so tools can be added or removed without changing the
generic executor in ``app.py``.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

import requests


def _gift(
    gift_id: str,
    name: str,
    category: str,
    price: int,
    personalities: list[str],
    interests: list[str],
    occasions: list[str],
    colors: list[str],
    relationships: list[str],
    meaning: str,
    caution: str = "Kiểm tra mẫu mã và thời gian giao hàng trước khi mua.",
) -> dict[str, Any]:
    return {
        "id": gift_id,
        "name": name,
        "category": category,
        "price": price,
        "gender": ["tất cả"],
        "personality_tags": personalities,
        "interest_tags": interests,
        "occasion_tags": occasions,
        "colors": colors,
        "relationship_tags": relationships,
        "meaning": meaning,
        "caution": caution,
    }


# Local reference catalog: prices are illustrative, not real-time quotations.
GIFT_DATABASE: list[dict[str, Any]] = [
    _gift("G001", "Đèn đọc sách mini", "Phụ kiện đọc sách", 280_000, ["hướng nội", "trầm tính", "thực tế"], ["đọc sách", "học tập"], ["sinh nhật", "tốt nghiệp"], ["đen", "trắng", "xanh"], ["bạn bè", "người thân", "người yêu"], "Thể hiện sự quan tâm đến những khoảng thời gian riêng và thói quen đọc sách."),
    _gift("G002", "Bình giữ nhiệt", "Đồ dùng hằng ngày", 350_000, ["thực tế", "năng động", "chu đáo"], ["thể thao", "du lịch", "đi học", "đi làm"], ["sinh nhật", "giáng sinh", "tốt nghiệp"], ["đen", "xanh", "hồng", "bạc"], ["bạn bè", "đồng nghiệp", "người thân"], "Lời nhắc chăm sóc sức khỏe thiết thực mỗi ngày."),
    _gift("G003", "Sổ tay bìa da và bút", "Văn phòng phẩm", 220_000, ["sáng tạo", "trầm tính", "ngăn nắp"], ["viết lách", "học tập", "vẽ"], ["sinh nhật", "tốt nghiệp", "thăng chức"], ["nâu", "đen", "xanh"], ["bạn bè", "đồng nghiệp", "người thân"], "Khuyến khích người nhận lưu lại ý tưởng và những cột mốc đáng nhớ."),
    _gift("G004", "Chậu cây để bàn", "Cây cảnh", 180_000, ["yêu thiên nhiên", "nhẹ nhàng", "thực tế"], ["trồng cây", "decor", "thiên nhiên"], ["sinh nhật", "tân gia", "thăng chức"], ["xanh", "trắng"], ["bạn bè", "đồng nghiệp", "người thân"], "Tượng trưng cho sự phát triển, bình an và sức sống mới.", "Kiểm tra người nhận có thời gian chăm cây hoặc có thú cưng hay không."),
    _gift("G005", "Bộ sách theo chủ đề", "Sách", 300_000, ["hướng nội", "ham học", "trầm tính"], ["đọc sách", "truyện", "học tập"], ["sinh nhật", "tốt nghiệp", "giáng sinh"], ["đa màu"], ["bạn bè", "người thân", "người yêu"], "Cho thấy bạn thực sự lắng nghe sở thích và trân trọng thế giới nội tâm của người nhận.", "Xác nhận các đầu sách người nhận đã sở hữu."),
    _gift("G006", "Nến thơm dịu nhẹ", "Thư giãn", 320_000, ["hướng nội", "lãng mạn", "tinh tế"], ["đọc sách", "decor", "thư giãn"], ["sinh nhật", "tân gia", "giáng sinh"], ["trắng", "hồng", "vàng"], ["bạn bè", "đồng nghiệp", "người yêu"], "Gửi tặng một khoảng nghỉ yên bình và ấm áp.", "Hỏi trước về dị ứng hoặc độ nhạy cảm với mùi hương."),
    _gift("G007", "Vé workshop thủ công", "Trải nghiệm", 450_000, ["sáng tạo", "hướng ngoại", "ưa trải nghiệm"], ["thủ công", "vẽ", "trải nghiệm"], ["sinh nhật", "kỷ niệm"], ["đa màu"], ["bạn bè", "người yêu", "người thân"], "Tạo cơ hội có thêm trải nghiệm và kỷ niệm chung.", "Kiểm tra lịch rảnh và địa điểm của người nhận."),
    _gift("G008", "Bộ cà phê pour-over", "Đồ uống", 650_000, ["tinh tế", "chill", "sáng tạo"], ["cà phê", "nấu ăn", "thư giãn"], ["sinh nhật", "giáng sinh", "tân gia"], ["đen", "bạc", "trắng"], ["bạn bè", "đồng nghiệp", "người thân"], "Mang đến một nghi thức thư giãn nhỏ trong nhịp sống hằng ngày."),
    _gift("G009", "Tai nghe Bluetooth mini", "Công nghệ", 480_000, ["hiện đại", "năng động", "hướng nội"], ["âm nhạc", "công nghệ", "thể thao"], ["sinh nhật", "tốt nghiệp"], ["đen", "trắng", "xanh"], ["bạn bè", "người thân", "người yêu"], "Thể hiện sự đồng điệu với sở thích âm nhạc và không gian riêng.", "Kiểm tra người nhận đã có tai nghe tương tự chưa."),
    _gift("G010", "Loa Bluetooth mini", "Công nghệ", 550_000, ["hướng ngoại", "năng động", "chill"], ["âm nhạc", "du lịch", "tiệc tùng"], ["sinh nhật", "tân gia", "giáng sinh"], ["đen", "xanh", "kem"], ["bạn bè", "người yêu", "người thân"], "Mang niềm vui và âm nhạc đến những cuộc gặp gỡ."),
    _gift("G011", "Khung ảnh cá nhân hóa", "Quà kỷ niệm", 250_000, ["tình cảm", "lãng mạn", "hoài niệm"], ["chụp ảnh", "decor", "lưu giữ kỷ niệm"], ["sinh nhật", "kỷ niệm", "valentine"], ["trắng", "nâu", "hồng"], ["người yêu", "bạn thân", "người thân"], "Lưu giữ một kỷ niệm chung và nhấn mạnh giá trị tình cảm."),
    _gift("G012", "Album ảnh scrapbook", "Quà kỷ niệm", 200_000, ["tình cảm", "sáng tạo", "hoài niệm"], ["chụp ảnh", "thủ công", "lưu giữ kỷ niệm"], ["sinh nhật", "kỷ niệm", "tốt nghiệp"], ["đa màu"], ["bạn thân", "người yêu", "người thân"], "Một món quà có công sức, kể lại hành trình và những ký ức đáng quý."),
    _gift("G013", "Móc khóa khắc tên", "Cá nhân hóa", 120_000, ["tình cảm", "tối giản", "thực tế"], ["phụ kiện", "du lịch"], ["sinh nhật", "kỷ niệm", "tốt nghiệp"], ["bạc", "đen", "hồng"], ["bạn bè", "người yêu", "người thân"], "Một dấu ấn cá nhân nhỏ gọn có thể mang theo mỗi ngày."),
    _gift("G014", "Hộp trà thảo mộc", "Đồ uống", 260_000, ["trầm tính", "tinh tế", "quan tâm sức khỏe"], ["thưởng trà", "sức khỏe", "thư giãn"], ["sinh nhật", "tết", "thăm hỏi"], ["xanh", "nâu", "trắng"], ["đồng nghiệp", "người thân", "bạn bè"], "Thể hiện lời chúc sức khỏe và những phút giây thư thái.", "Kiểm tra thành phần nếu người nhận có dị ứng hoặc đang dùng thuốc."),
    _gift("G015", "Bộ chăm sóc da cơ bản", "Chăm sóc cá nhân", 500_000, ["chỉn chu", "tinh tế", "quan tâm bản thân"], ["làm đẹp", "chăm sóc da"], ["sinh nhật", "8/3", "20/10"], ["trắng", "hồng", "xanh"], ["bạn thân", "người yêu", "người thân"], "Lời nhắn hãy dành thời gian chăm sóc và yêu thương bản thân.", "Cần biết loại da và tiền sử dị ứng của người nhận."),
    _gift("G016", "Túi tote canvas", "Thời trang", 190_000, ["trẻ trung", "tối giản", "thực tế"], ["thời trang", "đi học", "đọc sách"], ["sinh nhật", "tốt nghiệp"], ["trắng", "đen", "xanh"], ["bạn bè", "đồng nghiệp", "người thân"], "Món quà nhẹ nhàng, hữu dụng và đồng hành trong sinh hoạt hằng ngày."),
    _gift("G017", "Ví da tối giản", "Phụ kiện", 420_000, ["trưởng thành", "lịch sự", "tối giản"], ["thời trang", "công sở"], ["sinh nhật", "thăng chức", "tốt nghiệp"], ["đen", "nâu"], ["bạn bè", "đồng nghiệp", "người yêu"], "Tượng trưng cho sự ổn định, chỉn chu và lời chúc đủ đầy."),
    _gift("G018", "Bút ký cao cấp", "Văn phòng phẩm", 600_000, ["trưởng thành", "lịch sự", "tham vọng"], ["viết lách", "công việc", "học tập"], ["tốt nghiệp", "thăng chức", "sinh nhật"], ["đen", "bạc", "vàng"], ["đồng nghiệp", "sếp", "bạn bè"], "Đánh dấu một cột mốc và lời chúc thành công trên hành trình mới."),
    _gift("G019", "Bàn phím cơ mini", "Công nghệ", 1_200_000, ["hiện đại", "sáng tạo", "công nghệ"], ["lập trình", "game", "viết lách"], ["sinh nhật", "tốt nghiệp"], ["đen", "trắng", "xám"], ["bạn bè", "người yêu", "người thân"], "Nâng cấp góc làm việc và thể hiện sự thấu hiểu đam mê công nghệ."),
    _gift("G020", "Máy đọc sách", "Công nghệ", 3_200_000, ["hướng nội", "ham học", "tối giản"], ["đọc sách", "công nghệ", "học tập"], ["sinh nhật", "tốt nghiệp", "kỷ niệm"], ["đen", "xanh"], ["người yêu", "người thân", "bạn thân"], "Mở ra cả một thư viện và đồng hành lâu dài với thói quen đọc."),
    _gift("G021", "Bộ Lego sáng tạo", "Đồ chơi sáng tạo", 750_000, ["sáng tạo", "kiên nhẫn", "trẻ trung"], ["lego", "mô hình", "game"], ["sinh nhật", "giáng sinh"], ["đa màu"], ["bạn bè", "người yêu", "người thân"], "Khơi gợi trí tưởng tượng và mang lại niềm vui khi tự tay hoàn thiện."),
    _gift("G022", "Board game nhóm", "Giải trí", 380_000, ["hướng ngoại", "vui vẻ", "ưa kết nối"], ["board game", "game", "gặp gỡ bạn bè"], ["sinh nhật", "giáng sinh", "tân gia"], ["đa màu"], ["bạn bè", "đồng nghiệp", "người thân"], "Tạo thêm cơ hội kết nối, tiếng cười và kỷ niệm cùng nhau."),
    _gift("G023", "Thảm yoga", "Thể thao", 400_000, ["kỷ luật", "năng động", "quan tâm sức khỏe"], ["yoga", "thể thao", "tập gym"], ["sinh nhật", "năm mới"], ["tím", "xanh", "đen"], ["bạn bè", "người thân", "đồng nghiệp"], "Ủng hộ hành trình chăm sóc sức khỏe và cân bằng tinh thần."),
    _gift("G024", "Bộ dụng cụ làm bánh", "Ẩm thực", 470_000, ["sáng tạo", "kiên nhẫn", "ấm áp"], ["nấu ăn", "làm bánh", "thủ công"], ["sinh nhật", "tân gia", "giáng sinh"], ["hồng", "trắng", "bạc"], ["bạn bè", "người thân", "người yêu"], "Khuyến khích niềm vui sáng tạo và chia sẻ những món ngon."),
    _gift("G025", "Gối cổ du lịch", "Du lịch", 230_000, ["thực tế", "năng động", "ưa trải nghiệm"], ["du lịch", "dã ngoại"], ["sinh nhật", "chia tay", "tốt nghiệp"], ["xám", "xanh", "hồng"], ["bạn bè", "đồng nghiệp", "người thân"], "Một lời chúc cho những hành trình thoải mái và an toàn."),
    _gift("G026", "Bộ màu vẽ mini", "Nghệ thuật", 340_000, ["sáng tạo", "hướng nội", "nghệ sĩ"], ["vẽ", "nghệ thuật", "thủ công"], ["sinh nhật", "giáng sinh"], ["đa màu"], ["bạn bè", "người thân", "người yêu"], "Khuyến khích người nhận tự do biểu đạt và nuôi dưỡng cảm hứng."),
    _gift("G027", "Hộp nhạc gỗ", "Quà kỷ niệm", 290_000, ["lãng mạn", "hoài niệm", "nhẹ nhàng"], ["âm nhạc", "decor", "lưu giữ kỷ niệm"], ["sinh nhật", "kỷ niệm", "valentine"], ["nâu", "trắng", "hồng"], ["người yêu", "bạn thân", "người thân"], "Gợi lại một giai điệu và khoảnh khắc có ý nghĩa giữa hai người."),
    _gift("G028", "Khăn choàng mềm", "Thời trang", 360_000, ["tinh tế", "nhẹ nhàng", "lịch sự"], ["thời trang", "du lịch"], ["sinh nhật", "giáng sinh", "tết"], ["kem", "xám", "xanh", "hồng"], ["bạn bè", "người thân", "người yêu"], "Tượng trưng cho sự ấm áp, chở che và quan tâm."),
    _gift("G029", "Voucher nhà sách", "Voucher", 300_000, ["hướng nội", "ham học", "thực tế"], ["đọc sách", "học tập"], ["sinh nhật", "tốt nghiệp"], ["đa màu"], ["bạn bè", "đồng nghiệp", "người thân"], "Trao quyền lựa chọn đúng cuốn sách người nhận đang mong muốn."),
    _gift("G030", "Voucher trải nghiệm cà phê", "Trải nghiệm", 300_000, ["hướng ngoại", "chill", "ưa trải nghiệm"], ["cà phê", "gặp gỡ bạn bè", "chụp ảnh"], ["sinh nhật", "kỷ niệm"], ["đa màu"], ["bạn bè", "đồng nghiệp", "người yêu"], "Tặng một khoảng thời gian thư giãn và cơ hội tạo thêm kỷ niệm."),
]


PROFILE_DEFAULTS: dict[str, Any] = {
    "gender": "",
    "personality": [],
    "interests": [],
    "favorite_colors": [],
    "relationship": "",
    "closeness_level": None,
    "occasion": "",
    "budget_max": None,
    "budget_ambiguous": "",
    "dislikes": [],
    "already_owned": [],
    "preferred_styles": [],
    "accessibility_needs": [],
}


def _fold(text: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").replace("đ", "d")


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = _fold(value).strip()
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _contains_term(folded_text: str, term: str) -> bool:
    """Match a normalized term on word boundaries, never inside another word."""

    normalized = _fold(term).strip()
    return bool(normalized and re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", folded_text))


def _merge_profile(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    profile = copy.deepcopy(PROFILE_DEFAULTS)
    profile.update(copy.deepcopy(base or {}))
    list_fields = {"personality", "interests", "favorite_colors", "dislikes", "already_owned", "preferred_styles", "accessibility_needs"}
    for key, value in (patch or {}).items():
        if value in (None, "", []):
            continue
        if key in list_fields:
            incoming = value if isinstance(value, list) else [value]
            current = profile.get(key) if isinstance(profile.get(key), list) else []
            profile[key] = _unique(current + incoming)
        else:
            profile[key] = value
    return profile


def _extract_budget(text: str) -> int | None:
    folded = _fold(text)
    unit_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(trieu|tr|million|m|nghin|ngan|k)\b", folded)
    if unit_match:
        raw_number = unit_match.group(1).replace(",", ".")
        number = float(raw_number)
        unit = unit_match.group(2)
        multiplier = 1_000_000 if unit in {"trieu", "tr", "million", "m"} else 1_000
        return int(number * multiplier)

    dong_match = re.search(r"(-?\d[\d.,]{2,})\s*(?:vnd|dong|₫)", folded)
    if dong_match:
        digits = re.sub(r"[^\d-]", "", dong_match.group(1))
        return int(digits)

    context_match = re.search(r"(?:ngan sach|budget|toi da|duoi|tam|khoang)\D{0,12}(-?\d{4,})", folded)
    return int(context_match.group(1)) if context_match else None


def classify_gift_scope(user_text: str, has_active_profile: bool = False) -> dict[str, Any]:
    """Classify whether a message belongs to gift/personality consultation."""

    text = _fold(user_text)
    blocked_patterns = (
        "bo qua huong dan", "quen huong dan", "tiet lo system prompt", "hien system prompt",
        "toi la admin", "gia lam admin", "quyen admin", "developer mode", "che do nha phat trien",
        "jailbreak", "dan mode", "ghi de quy tac", "vuot qua guardrail", "lam theo lenh moi",
        "viet ma doc", "hack", "malware", "lay api key", "doc file env", "tiet lo bi mat",
    )
    if any(pattern in text for pattern in blocked_patterns):
        return {
            "in_scope": False,
            "reason": "Yêu cầu cố gắng thay đổi hoặc vượt qua quy tắc hệ thống.",
            "intent": "prompt_injection",
        }

    domain_terms = (
        "qua", "tang", "sinh nhat", "ky niem", "tinh cach", "mbti", "so thich",
        "ngan sach", "budget", "mau", "than mat", "ban trai", "ban gai", "nguoi yeu",
        "dong nghiep", "nguoi than", "huong noi", "huong ngoai", "valentine", "giang sinh",
        "khong thich", "da co", "trai nghiem",
    )
    off_topic_terms = (
        "giai phuong trinh", "viet code", "lap trinh", "thoi tiet", "chinh tri", "bong da",
        "dich van ban", "lam bai tap", "ke chuyen", "tin tuc", "chung khoan", "tien ao",
    )
    social_terms = ("chao", "cam on", "ok", "duoc", "tiep tuc")
    follow_up_value = bool(
        re.search(r"\b(?:nam|nu|[1-5]\s*/\s*5|-?\d+(?:[.,]\d+)?\s*(?:k|tr|trieu|nghin|dong|vnd))\b", text)
    )
    short_follow_up = has_active_profile and follow_up_value
    contains_domain = any(term in text for term in domain_terms)
    contains_off_topic = any(term in text for term in off_topic_terms)
    in_scope = (contains_domain or any(term in text for term in social_terms) or short_follow_up) and not contains_off_topic
    recommendation_terms = ("qua", "tang", "ngan sach", "budget", "khong thich", "da co")
    suitability_patterns = (
        "co the tang", "co nen tang", "tang duoc khong", "phu hop khong", "co hop khong",
        "co duoc khong", "nen chon", "mon nay co",
    )
    accessibility_terms = ("nguoi mu", "khiem thi", "khong nhin thay", "nguoi diec", "khiem thinh", "khuyet tat")
    concrete_gift_terms = (
        "den doc sach", "sach in", "nuoc hoa", "nen thom", "tai nghe", "loa", "dong ho",
        "giay", "quan ao", "ban phim", "binh giu nhiet", "cay canh",
    )
    accessibility_suitability = (
        any(term in text for term in accessibility_terms)
        and any(term in text for term in concrete_gift_terms)
        and "tang" in text
    )
    explicit_recommendation = any(
        pattern in text for pattern in ("tim qua", "goi y qua", "tu van qua", "top 3", "ngan sach", "budget")
    )
    knowledge_question = (
        ("tinh cach" in text or "mbti" in text)
        and any(pattern in text for pattern in ("la gi", "thuong", "phong cach", "y nghia", "nhu the nao"))
        and not explicit_recommendation
    )
    if any(pattern in text for pattern in suitability_patterns) or accessibility_suitability:
        intent = "gift_suitability"
    elif knowledge_question:
        intent = "personality_knowledge"
    elif has_active_profile and (short_follow_up or any(term in text for term in recommendation_terms)):
        intent = "profile_update"
    elif any(term in text for term in recommendation_terms):
        intent = "gift_recommendation"
    elif "tinh cach" in text or "mbti" in text:
        intent = "personality_knowledge"
    elif any(term in text for term in social_terms):
        intent = "conversation"
    elif contains_off_topic:
        intent = "out_of_scope"
    else:
        intent = "out_of_scope"
    return {
        "in_scope": in_scope,
        "reason": "Thuộc tư vấn quà/tính cách." if in_scope else "Không liên quan đến tư vấn tính cách hoặc chọn quà.",
        "intent": intent,
    }


def extract_recipient_profile(
    user_text: str,
    current_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract and merge recipient facts from one Vietnamese user message."""

    if not isinstance(user_text, str) or not user_text.strip():
        return {"success": False, "error": "user_text phải là chuỗi không rỗng."}

    folded = _fold(user_text)
    patch: dict[str, Any] = {}

    if re.search(r"\b(nu|ban gai|chi gai|me|vo|co ay)\b", folded):
        patch["gender"] = "nữ"
    elif re.search(r"\b(nam|ban trai|anh trai|bo|chong|cau ay)\b", folded):
        patch["gender"] = "nam"
    elif "khong muon xac dinh" in folded or "phi nhi nguyen" in folded:
        patch["gender"] = "không xác định"

    vocabularies = {
        "personality": ["hướng nội", "hướng ngoại", "trầm tính", "điềm tĩnh", "năng động", "sáng tạo", "thực tế", "lãng mạn", "tinh tế", "vui vẻ", "tối giản", "ưa trải nghiệm", "nhẹ nhàng", "công nghệ", "kỷ luật", "tình cảm"],
        "interests": ["đọc sách", "truyện", "công nghệ", "âm nhạc", "thể thao", "chạy bộ", "tập gym", "du lịch", "chụp ảnh", "nấu ăn", "làm bánh", "cà phê", "thưởng trà", "vẽ", "nghệ thuật", "game", "lego", "board game", "trồng cây", "decor", "làm đẹp", "thời trang", "lập trình", "viết lách", "yoga", "thủ công"],
        "favorite_colors": ["xanh dương", "xanh", "đỏ", "hồng", "đen", "trắng", "vàng", "tím", "cam", "nâu", "xám", "bạc", "kem"],
        "preferred_styles": ["thực tế", "tình cảm", "độc đáo", "sáng tạo", "dùng hằng ngày", "trải nghiệm", "tối giản", "sang trọng"],
    }
    for field, values in vocabularies.items():
        matches = [value for value in values if _contains_term(folded, value)]
        if matches:
            patch[field] = matches

    accessibility_map = {
        "khiếm thị": ["nguoi mu", "khiem thi", "khong nhin thay"],
        "khiếm thính": ["nguoi diec", "khiem thinh", "khong nghe thay"],
        "hạn chế vận động": ["han che van dong", "khuyet tat van dong", "xe lan"],
    }
    accessibility_needs = [
        need for need, terms in accessibility_map.items() if any(term in folded for term in terms)
    ]
    if accessibility_needs:
        patch["accessibility_needs"] = accessibility_needs

    relationship_map = {
        "người yêu": ["nguoi yeu", "ban trai", "ban gai", "vo", "chong"],
        "bạn thân": ["ban than"],
        "bạn bè": ["ban toi", "ban be", "nguoi ban"],
        "đồng nghiệp": ["dong nghiep", "sep"],
        "người thân": ["nguoi than", "me", "bo", "anh trai", "chi gai", "em trai", "em gai"],
    }
    for relationship, terms in relationship_map.items():
        if any(term in folded for term in terms):
            patch["relationship"] = relationship
            break

    occasion_map = {
        "sinh nhật": ["sinh nhat"], "kỷ niệm": ["ky niem"], "tốt nghiệp": ["tot nghiep"],
        "giáng sinh": ["giang sinh", "noel"], "tân gia": ["tan gia"], "valentine": ["valentine"],
        "8/3": ["8/3"], "20/10": ["20/10"], "tết": ["tet"], "thăng chức": ["thang chuc"],
    }
    for occasion, terms in occasion_map.items():
        if any(term in folded for term in terms):
            patch["occasion"] = occasion
            break

    closeness_match = re.search(r"(?:than mat|than thiet|muc|do than)\D{0,8}([1-5])(?:\s*/\s*5)?", folded)
    if not closeness_match:
        closeness_match = re.search(r"\b([1-5])\s*/\s*5\b", folded)
    if closeness_match:
        patch["closeness_level"] = int(closeness_match.group(1))

    budget = _extract_budget(user_text)
    if budget is not None:
        patch["budget_max"] = budget
    else:
        ambiguous_budget = re.search(r"(?:ngan sach|budget|toi da|duoi|tam|khoang)\D{0,10}(\d{1,3})\b", folded)
        if ambiguous_budget:
            patch["budget_ambiguous"] = ambiguous_budget.group(1)

    exclusion_terms = ["sách", "nước hoa", "tai nghe", "mỹ phẩm", "cây", "quần áo", "đồ công nghệ"]
    if any(phrase in folded for phrase in ("khong thich", "khong muon", "tranh")):
        patch["dislikes"] = [term for term in exclusion_terms if _fold(term) in folded]
    if any(phrase in folded for phrase in ("da co", "so huu roi", "co nhieu")):
        patch["already_owned"] = [term for term in exclusion_terms if _fold(term) in folded]

    profile = _merge_profile(current_profile or {}, patch)
    if profile.get("budget_max") is not None:
        profile["budget_ambiguous"] = ""
    return {
        "success": True,
        "profile": profile,
        "updated_fields": sorted(patch),
        "assessment": assess_profile(profile),
    }


def assess_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate hard fields and describe missing/optional information."""

    if not isinstance(profile, dict):
        return {"success": False, "error": "profile phải là object."}
    missing: list[str] = []
    if not str(profile.get("gender") or "").strip():
        missing.append("gender")
    if not profile.get("personality") and not profile.get("preferred_styles"):
        missing.append("personality")
    budget = profile.get("budget_max")
    if budget is None:
        missing.append("budget_max")
    elif not isinstance(budget, (int, float)) or budget <= 0:
        return {"success": False, "status": "invalid", "error": "Ngân sách phải là số dương.", "missing_fields": []}
    closeness = profile.get("closeness_level")
    if closeness is not None and (not isinstance(closeness, int) or not 1 <= closeness <= 5):
        return {"success": False, "status": "invalid", "error": "Độ thân mật phải nằm trong khoảng 1–5.", "missing_fields": []}

    optional = [field for field in ("interests", "favorite_colors", "relationship", "closeness_level", "occasion") if not profile.get(field)]
    questions = {
        "gender": "Người nhận có giới tính hoặc cách xưng hô như thế nào?",
        "personality": "Người nhận có tính cách/phong cách nào nổi bật (ví dụ hướng nội, năng động, thực tế hay tình cảm)?",
        "budget_max": (
            f"Bạn nói ngân sách {profile.get('budget_ambiguous')}; đó là "
            f"{profile.get('budget_ambiguous')} nghìn đồng hay một mức khác?"
            if profile.get("budget_ambiguous")
            else "Ngân sách tối đa bạn có thể chi là bao nhiêu?"
        ),
    }
    return {
        "success": True,
        "status": "need_more_information" if missing else "complete",
        "missing_fields": missing,
        "optional_fields": optional,
        "suggested_questions": [questions[field] for field in missing],
        "occasion_question": "Bạn định tặng quà vào dịp gì?" if not profile.get("occasion") else "",
    }


def search_gift_catalog(profile: dict[str, Any], max_results: int = 15) -> dict[str, Any]:
    """Search the local catalog using soft profile signals; no hard rejection."""

    assessment = assess_profile(profile)
    if not assessment.get("success") or assessment.get("status") != "complete":
        return {"success": False, "error": assessment.get("error") or "Hồ sơ chưa đủ thông tin tối thiểu.", "assessment": assessment}

    folded_personality = [_fold(value) for value in profile.get("personality", []) + profile.get("preferred_styles", [])]
    folded_interests = [_fold(value) for value in profile.get("interests", [])]
    occasion = _fold(profile.get("occasion"))
    color_terms = [_fold(value) for value in profile.get("favorite_colors", [])]

    scored: list[dict[str, Any]] = []
    for gift in GIFT_DATABASE:
        gift_copy = copy.deepcopy(gift)
        preliminary = 0
        preliminary += 3 * sum(tag in folded_interests for tag in map(_fold, gift["interest_tags"]))
        preliminary += 2 * sum(tag in folded_personality for tag in map(_fold, gift["personality_tags"]))
        preliminary += 2 if occasion and occasion in map(_fold, gift["occasion_tags"]) else 0
        preliminary += sum(tag in color_terms for tag in map(_fold, gift["colors"]))
        gift_copy["preliminary_score"] = preliminary
        scored.append(gift_copy)
    scored.sort(key=lambda item: (item["preliminary_score"], -item["price"]), reverse=True)
    return {"success": True, "candidates": scored[: max(3, min(int(max_results), 30))]}


def check_gift_constraints(candidates: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Apply budget, dislikes and already-owned constraints without crashing."""

    if not isinstance(candidates, list):
        return {"success": False, "error": "candidates phải là list."}
    budget = profile.get("budget_max")
    if not isinstance(budget, (int, float)) or budget <= 0:
        return {"success": False, "error": "Ngân sách không hợp lệ."}

    excluded = [_fold(value) for value in profile.get("dislikes", []) + profile.get("already_owned", [])]
    accessibility = {_fold(value) for value in profile.get("accessibility_needs", [])}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gift in candidates:
        reasons: list[str] = []
        if gift.get("price", budget + 1) > budget:
            reasons.append("Vượt ngân sách tối đa.")
        searchable = _fold(f"{gift.get('name', '')} {gift.get('category', '')}")
        if "khiem thi" in accessibility and any(
            term in searchable for term in ("den doc sach", "bo sach", "voucher nha sach")
        ):
            reasons.append("Không phù hợp nhu cầu tiếp cận của người khiếm thị.")
        for term in excluded:
            if term and term in searchable:
                reasons.append(f"Thuộc nhóm đã loại trừ/đã sở hữu: {term}.")
        if reasons:
            rejected.append({"gift_id": gift.get("id"), "name": gift.get("name"), "reasons": reasons})
        else:
            accepted.append(copy.deepcopy(gift))
    return {"success": True, "accepted": accepted, "rejected": rejected}


def rank_and_diversify_gifts(
    profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    top_k: int = 3,
) -> dict[str, Any]:
    """Score candidates on 100 points and prefer different gift categories."""

    if not isinstance(candidates, list):
        return {"success": False, "error": "candidates phải là list."}
    if not candidates:
        return {"success": False, "error": "Không có ứng viên hợp lệ trong ngân sách."}

    personality = {_fold(value) for value in profile.get("personality", []) + profile.get("preferred_styles", [])}
    interests = {_fold(value) for value in profile.get("interests", [])}
    colors = {_fold(value) for value in profile.get("favorite_colors", [])}
    occasion = _fold(profile.get("occasion"))
    relationship = _fold(profile.get("relationship"))
    budget = float(profile.get("budget_max") or 1)

    ranked: list[dict[str, Any]] = []
    for gift in candidates:
        folded_gift_interests = {_fold(value) for value in gift.get("interest_tags", [])}
        folded_gift_personalities = {_fold(value) for value in gift.get("personality_tags", [])}
        interest_matches = interests.intersection(folded_gift_interests)
        personality_matches = personality.intersection(folded_gift_personalities)
        color_matches = colors.intersection(map(_fold, gift.get("colors", [])))
        score_interest = min(30, 15 * len(interest_matches)) if interests else 12
        score_personality = min(25, 13 * len(personality_matches)) if personality else 8
        ratio = float(gift.get("price", budget)) / budget
        score_budget = 15 if 0.55 <= ratio <= 1 else 12 if ratio >= 0.3 else 9
        score_occasion = 10 if occasion and occasion in map(_fold, gift.get("occasion_tags", [])) else 6 if not occasion else 2
        score_relationship = 10 if relationship and relationship in map(_fold, gift.get("relationship_tags", [])) else 6 if not relationship else 3
        score_color = 5 if color_matches else 2 if not colors else 0
        score = min(100, score_interest + score_personality + score_budget + score_occasion + score_relationship + score_color + 5)
        reasons = []
        if interest_matches:
            displayed = [value for value in profile.get("interests", []) if _fold(value) in interest_matches]
            reasons.append("Khớp sở thích: " + ", ".join(displayed))
        if personality_matches:
            displayed = [
                value
                for value in profile.get("personality", []) + profile.get("preferred_styles", [])
                if _fold(value) in personality_matches
            ]
            reasons.append("Phù hợp tính cách/phong cách: " + ", ".join(displayed))
        reasons.append("Nằm trong ngân sách đã đặt ra")
        if occasion and score_occasion == 10:
            reasons.append(f"Phù hợp dịp {profile.get('occasion')}")
        item = copy.deepcopy(gift)
        item.update({"score": int(score), "reasons": reasons, "cautions": [gift.get("caution")]})
        ranked.append(item)
    ranked.sort(key=lambda item: (item["score"], item.get("preliminary_score", 0)), reverse=True)

    selected: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    used_interest_tags: set[str] = set()
    for gift in ranked:
        broad_category = _fold(gift["category"].split("/")[0])
        gift_interest_tags = {_fold(value) for value in gift.get("interest_tags", [])}
        overlap_ratio = len(gift_interest_tags.intersection(used_interest_tags)) / max(len(gift_interest_tags), 1)
        if broad_category not in used_categories and (not selected or overlap_ratio < 0.67):
            selected.append(gift)
            used_categories.add(broad_category)
            used_interest_tags.update(gift_interest_tags)
        if len(selected) == top_k:
            break
    if len(selected) < top_k:
        for gift in ranked:
            if gift not in selected:
                selected.append(gift)
            if len(selected) == top_k:
                break
    for rank, gift in enumerate(selected, start=1):
        gift["rank"] = rank
    return {"success": True, "recommendations": selected, "count": len(selected)}


def update_profile_from_feedback(
    current_profile: dict[str, Any],
    previous_recommendations: list[dict[str, Any]],
    feedback: str,
) -> dict[str, Any]:
    """Merge constraints/preferences found in feedback into the current profile."""

    extraction = extract_recipient_profile(feedback, current_profile)
    if not extraction.get("success"):
        return extraction
    return {
        "success": True,
        "profile": extraction["profile"],
        "assessment": extraction.get("assessment", assess_profile(extraction["profile"])),
        "previous_recommendation_ids": [item.get("id") for item in previous_recommendations if isinstance(item, dict)],
        "updated_fields": extraction.get("updated_fields", []),
    }


def _image_search_query(gift: dict[str, Any]) -> str:
    """Convert catalog names into broad English Commons search terms."""

    text = _fold(f"{gift.get('name', '')} {gift.get('category', '')}")
    mappings = (
        (("den doc sach",), "reading lamp"), (("binh giu nhiet",), "thermos bottle"),
        (("so tay", "but ky"), "notebook pen"), (("chau cay",), "indoor potted plant"),
        (("sach", "nha sach"), "books reading"), (("nen thom",), "scented candle"),
        (("workshop", "scrapbook"), "arts and crafts"), (("ca phe",), "coffee brewing"),
        (("tai nghe",), "wireless headphones"), (("loa bluetooth",), "portable speaker"),
        (("khung anh", "album anh"), "photo album"), (("tra thao moc",), "herbal tea"),
        (("cham soc da",), "skin care products"), (("tui tote",), "canvas tote bag"),
        (("vi da",), "leather wallet"), (("ban phim",), "computer keyboard"),
        (("lego",), "building blocks toy"), (("board game",), "board game"),
        (("yoga",), "yoga mat"), (("lam banh",), "baking tools"),
        (("goi co",), "travel neck pillow"), (("mau ve",), "artist paint set"),
        (("hop nhac",), "wooden music box"), (("khan choang",), "scarf"),
    )
    for keywords, query in mappings:
        if any(keyword in text for keyword in keywords):
            return query
    return "gift present"


GIFT_LOGIC_CONFLICTS = [
        {
            "gift_terms": ("den doc sach", "sach in"),
            "recipient_terms": ("nguoi mu", "khiem thi"),
            "suitable": False,
            "verdict": "Không nên chọn làm món quà chính",
            "reason": "Món quà phụ thuộc vào thị giác nên không mang lại công dụng trực tiếp cho người khiếm thị.",
            "alternatives": ["sách nói hoặc gói audiobook", "loa thông minh điều khiển bằng giọng nói", "quà xúc giác hoặc trải nghiệm âm nhạc"],
            "check_before_buying": "Hỏi người nhận về thiết bị hỗ trợ và sở thích âm thanh họ đang sử dụng.",
        },
        {
            "gift_terms": ("nen thom", "nuoc hoa", "tinh dau"),
            "recipient_terms": ("di ung", "hen suyen", "nhay cam mui"),
            "suitable": False,
            "verdict": "Nên tránh",
            "reason": "Mùi hương có thể gây khó chịu hoặc làm nặng phản ứng dị ứng/hô hấp.",
            "alternatives": ["đồ dùng không mùi", "voucher tự chọn", "quà cá nhân hóa không chứa hương liệu"],
            "check_before_buying": "Xác nhận tình trạng dị ứng và thành phần sản phẩm.",
        },
        {
            "gift_terms": ("banh", "keo", "do an"),
            "recipient_terms": ("tieu duong", "di ung thuc pham"),
            "suitable": False,
            "verdict": "Cần đổi hoặc kiểm tra kỹ",
            "reason": "Thực phẩm có thể không phù hợp với chế độ ăn hoặc tình trạng dị ứng của người nhận.",
            "alternatives": ["quà phi thực phẩm", "voucher tự chọn", "sản phẩm có nhãn thành phần rõ ràng"],
            "check_before_buying": "Hỏi rõ chế độ ăn và thành phần cần tránh.",
        },
    ]


def _find_gift_logic_conflict(text: str) -> dict[str, Any] | None:
    for rule in GIFT_LOGIC_CONFLICTS:
        if any(term in text for term in rule["gift_terms"]) and any(term in text for term in rule["recipient_terms"]):
            return {key: value for key, value in rule.items() if not key.endswith("_terms")}
    return None


def precheck_request_logic(user_text: str, recent_context: str = "") -> dict[str, Any]:
    """Deterministic guardrail run before the tool registry or recommendation pipeline."""

    if not isinstance(user_text, str) or not user_text.strip():
        return {"decision": "allow", "source": "guardrail"}
    current = _fold(user_text)
    injection_patterns = (
        "bo qua huong dan", "tiet lo system prompt", "hien system prompt", "toi la admin",
        "gia lam admin", "quyen admin", "developer mode", "ghi de quy tac", "vuot qua guardrail",
        "lay api key", "doc file env", "tiet lo bi mat", "jailbreak", "dan mode",
    )
    if any(pattern in current for pattern in injection_patterns):
        return {
            "decision": "prompt_injection",
            "confidence": 1.0,
            "source": "guardrail",
            "verdict": "Yêu cầu cố gắng vượt qua quy tắc hệ thống",
        }
    combined = current
    # Join a prior fragment only when the current message supplies one side of a
    # gift/recipient constraint. This avoids reviving a conflict from an old turn.
    gift_terms = tuple(term for rule in GIFT_LOGIC_CONFLICTS for term in rule["gift_terms"])
    recipient_terms = tuple(term for rule in GIFT_LOGIC_CONFLICTS for term in rule["recipient_terms"])
    if recent_context and (
        (any(term in current for term in gift_terms) and not any(term in current for term in recipient_terms))
        or (any(term in current for term in recipient_terms) and not any(term in current for term in gift_terms))
    ):
        combined = f"{_fold(recent_context)} {current}"
    conflict = _find_gift_logic_conflict(combined)
    if conflict:
        return {"decision": "conflict", "confidence": 1.0, "source": "guardrail", **conflict}
    return {"decision": "allow", "confidence": 1.0, "source": "guardrail"}


def evaluate_gift_suitability(user_text: str) -> dict[str, Any]:
    """Evaluate whether a proposed gift conflicts with accessibility or safety needs."""

    if not isinstance(user_text, str) or not user_text.strip():
        return {"success": False, "error": "Cần mô tả món quà và người nhận."}
    conflict = _find_gift_logic_conflict(_fold(user_text))
    if conflict:
        return {"success": True, **conflict}

    return {
        "success": True,
        "suitable": None,
        "verdict": "Chưa đủ dữ liệu để kết luận chắc chắn",
        "reason": "Cần cân nhắc khả năng sử dụng, sở thích, điều đã sở hữu và các yêu cầu tiếp cận/an toàn của người nhận.",
        "alternatives": [],
        "check_before_buying": "Hỏi người nhận hoặc người thân về nhu cầu thực tế trước khi mua.",
    }


def inspect_gift_idea(user_text: str) -> dict[str, Any]:
    """Inspect one concrete gift idea and return usage/occasion context for the Agent.

    Use this for questions such as "tặng đèn đọc sách cho bạn nữ sinh nhật có
    được không?". It does not require the minimum profile used by Top-3 search.
    Direct accessibility or safety conflicts take precedence over soft matches.
    """

    if not isinstance(user_text, str) or not user_text.strip():
        return {"success": False, "error": "Cần mô tả ý tưởng quà và người nhận."}
    folded = _fold(user_text)
    conflict = _find_gift_logic_conflict(folded)
    if conflict:
        return {"success": True, "status": "conflict", **conflict}

    matched: dict[str, Any] | None = None
    for gift in GIFT_DATABASE:
        name = _fold(gift["name"])
        significant_tokens = [token for token in name.split() if len(token) >= 3 and token not in {"mini", "theo", "cua"}]
        if name in folded or (len(significant_tokens) >= 2 and all(token in folded for token in significant_tokens[:2])):
            matched = copy.deepcopy(gift)
            break
    if matched is None:
        return {
            "success": True,
            "status": "unknown_gift",
            "verdict": "Có thể cân nhắc nhưng chưa đủ căn cứ",
            "reason": "Ý tưởng này chưa có trong catalog tham chiếu nên cần xác minh công dụng và khả năng sử dụng thực tế.",
            "questions_to_verify": [
                "Người nhận có thực sự sử dụng hoặc mong muốn món này không?",
                "Món quà có yêu cầu sức khỏe, kích thước hoặc thiết bị tương thích nào không?",
            ],
        }

    detected_occasions = [occasion for occasion in matched["occasion_tags"] if _fold(occasion) in folded]
    interest_signals = [
        interest
        for interest in matched["interest_tags"]
        if any(
            marker in folded
            for marker in (
                f"thich {_fold(interest)}",
                f"thuong {_fold(interest)}",
                f"dam me {_fold(interest)}",
                f"so thich {_fold(interest)}",
            )
        )
    ]
    suitable_occasion = bool(detected_occasions)
    questions: list[str] = []
    if not interest_signals:
        primary_interest = matched["interest_tags"][0] if matched["interest_tags"] else "công dụng của món quà"
        questions.append(f"Người nhận có hứng thú với {primary_interest} hoặc thường dùng món tương tự không?")
    questions.append("Người nhận đã có món tương tự hoặc có nhu cầu tiếp cận/an toàn đặc biệt không?")
    positives = []
    if suitable_occasion:
        positives.append(f"Phù hợp dịp {detected_occasions[0]}")
    if interest_signals:
        positives.append("Khớp tín hiệu sở thích: " + ", ".join(interest_signals))
    if not positives:
        positives.append("Đây là món quà có công dụng rõ ràng nếu đúng nhu cầu người nhận")
    return {
        "success": True,
        "status": "reasonable_with_conditions",
        "verdict": "Có thể tặng nếu phù hợp nhu cầu thực tế",
        "gift": {
            "id": matched["id"],
            "name": matched["name"],
            "reference_price": matched["price"],
            "category": matched["category"],
            "intended_interests": matched["interest_tags"],
            "suitable_occasions": matched["occasion_tags"],
            "meaning": matched["meaning"],
        },
        "positive_signals": positives,
        "reason": "Giới tính không tự quyết định độ phù hợp; công dụng, sở thích và khả năng sử dụng mới là tín hiệu chính.",
        "questions_to_verify": questions,
        "check_before_buying": matched["caution"],
    }


def search_gift_images(
    gifts: list[dict[str, Any]],
    max_images: int = 3,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    """Search Wikimedia Commons for one illustrative image per recommended gift.

    This read-only network tool is optional and must only be called after user
    consent. It returns source links and never changes recommendation scores.
    """

    if not isinstance(gifts, list) or not gifts:
        return {"success": False, "error": "Chưa có danh sách quà để tìm ảnh.", "images": []}

    endpoint = "https://commons.wikimedia.org/w/api.php"
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    limit = max(1, min(int(max_images), 3))
    headers = {"User-Agent": "GiftSenseAgent/1.0 (educational project)"}

    for gift in gifts[:limit]:
        gift_name = str(gift.get("name") or gift.get("gift_name") or "Món quà")
        query = _image_search_query(gift)
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 900,
        }
        try:
            response = requests.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=max(1, int(timeout_seconds)),
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            selected: dict[str, Any] | None = None
            for page in sorted(pages.values(), key=lambda item: item.get("index", 999)):
                info_list = page.get("imageinfo") or []
                if not info_list:
                    continue
                info = info_list[0]
                mime = str(info.get("mime", ""))
                image_url = info.get("thumburl") or info.get("url")
                if image_url and mime.startswith("image/") and mime != "image/svg+xml":
                    metadata = info.get("extmetadata") or {}
                    selected = {
                        "gift_name": gift_name,
                        "query": query,
                        "image_url": image_url,
                        "source_url": info.get("descriptionurl") or info.get("url"),
                        "source": "Wikimedia Commons",
                        "license": (metadata.get("LicenseShortName") or {}).get("value", "Xem tại nguồn"),
                        "file_title": page.get("title", ""),
                    }
                    break
            if selected:
                images.append(selected)
            else:
                errors.append({"gift_name": gift_name, "error": "Không tìm thấy ảnh phù hợp."})
        except requests.Timeout:
            errors.append({"gift_name": gift_name, "error": "Tìm ảnh bị timeout."})
        except requests.RequestException:
            errors.append({"gift_name": gift_name, "error": "Không thể kết nối dịch vụ ảnh."})
        except (TypeError, ValueError, KeyError):
            errors.append({"gift_name": gift_name, "error": "Dữ liệu ảnh trả về không hợp lệ."})

    return {
        "success": bool(images),
        "images": images,
        "errors": errors,
        "notice": "Ảnh chỉ mang tính minh họa; hãy kiểm tra sản phẩm thực tế trước khi mua.",
    }


AVAILABLE_TOOLS = {
    "classify_gift_scope": classify_gift_scope,
    "extract_recipient_profile": extract_recipient_profile,
    "assess_profile": assess_profile,
    "search_gift_catalog": search_gift_catalog,
    "check_gift_constraints": check_gift_constraints,
    "rank_and_diversify_gifts": rank_and_diversify_gifts,
    "update_profile_from_feedback": update_profile_from_feedback,
    "evaluate_gift_suitability": evaluate_gift_suitability,
    "inspect_gift_idea": inspect_gift_idea,
    "search_gift_images": search_gift_images,
}
