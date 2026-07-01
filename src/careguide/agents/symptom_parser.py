from __future__ import annotations

import re
from collections.abc import Iterable

from careguide.schemas.clinical import ParsedClinicalInfo


NEGATION_MARKERS = ("không", "khong", "chưa", "chua", "chưa ghi nhận", "phủ nhận")

SEVERITY_TERMS = (
    "nhẹ",
    "hơi",
    "nhiều",
    "rất",
    "dữ dội",
    "tăng dần",
    "đột ngột",
    "liên tục",
    "kéo dài",
    "tái diễn",
    "âm ỉ",
    "nặng",
)

RISK_FACTOR_TERMS = {
    "trẻ nhỏ": ("trẻ", "em bé", "con tôi", "3 tuổi", "8 tháng"),
    "người già": ("người già", "72 tuổi", "75 tuổi", "70 tuổi", "68 tuổi"),
    "thai kỳ": ("mang thai", "thai", "trễ kinh"),
    "đái tháo đường": ("tiểu đường", "đái tháo đường"),
    "bệnh hen": ("bị hen", "hen"),
    "thuốc chống đông": ("thuốc chống đông",),
    "chấn thương": ("tai nạn", "ngã", "chấn thương", "va nhẹ", "vết cắt"),
    "ngộ độc": ("uống nhầm", "uống nhiều thuốc", "hóa chất"),
}

SYMPTOM_TERMS = (
    "không nói được thành câu",
    "phải ngồi cúi người để thở",
    "đau hông lưng dữ dội từng cơn",
    "đau đầu dữ dội đột ngột",
    "đau ngực ép nặng",
    "đau bụng dưới dữ dội",
    "đau bụng dưới",
    "đau bụng dữ dội",
    "đau bụng tăng dần",
    "đau bụng từng cơn",
    "đau bụng lâm râm",
    "đau bụng âm ỉ",
    "đau bụng",
    "đau dạ dày âm ỉ",
    "đau họng dữ dội",
    "đau họng nhẹ",
    "đau rát khi nuốt",
    "đau vùng hông lưng",
    "đau vùng mặt",
    "đau khớp gối",
    "đau cổ vai gáy",
    "đau cổ vai nhẹ",
    "đau cổ tay nhẹ",
    "đau nhẹ ở cổ tay",
    "đau vai khi nâng tay",
    "đau gót chân",
    "đau răng âm ỉ",
    "đau mắt dữ dội",
    "đau mắt đỏ",
    "đau mắt nhẹ",
    "đau tai nhiều",
    "đau tai nhẹ",
    "đau lưng dưới",
    "đau lưng",
    "mỏi lưng",
    "đau đầu nhiều hơn mọi ngày",
    "đau đầu âm ỉ",
    "đau đầu",
    "đau ngực dữ dội",
    "đau ngực đột ngột",
    "đau ngực nhẹ khi ho",
    "đau ngực khi gắng sức",
    "đau ngực",
    "đau lan lên hàm",
    "khó thở khi đi lại",
    "khó thở nhiều",
    "khó thở",
    "thở chậm",
    "thở rít",
    "môi hơi tím",
    "môi tím",
    "tím tái",
    "sốt cao",
    "sốt nhẹ",
    "sốt",
    "ho ra đờm lẫn máu",
    "ho đờm vàng",
    "ho khan nhẹ",
    "ho khan",
    "ho nhẹ",
    "ho nhiều",
    "ho ít",
    "ho",
    "đau họng",
    "sổ mũi",
    "hắt hơi",
    "ngứa mũi",
    "nghẹt mũi nhẹ",
    "nghẹt mũi",
    "khàn tiếng",
    "mệt mỏi kéo dài",
    "mệt lả",
    "mệt nhiều",
    "mệt",
    "uống nước kém",
    "bỏ ăn",
    "quấy khóc nhiều",
    "ăn uống bình thường",
    "buồn nôn",
    "nôn ói liên tục",
    "nôn ra máu đỏ tươi",
    "nôn ra máu",
    "nôn nhiều",
    "nôn",
    "tiêu chảy ra máu",
    "tiêu chảy nhiều lần",
    "tiêu chảy",
    "đi ngoài phân đen",
    "đi ngoài ra máu",
    "đầy hơi",
    "ợ nóng",
    "ợ hơi",
    "trào ngược",
    "nóng rát sau xương ức",
    "táo bón tái diễn",
    "táo bón",
    "khát nhiều",
    "chóng mặt khi đứng dậy",
    "chóng mặt muốn ngất",
    "chóng mặt xoay vòng dữ dội",
    "chóng mặt thoáng qua",
    "chóng mặt",
    "ngất",
    "choáng váng",
    "lơ mơ",
    "mất ý thức",
    "không đáp ứng rõ",
    "co giật",
    "méo miệng",
    "nói khó",
    "yếu nửa người",
    "yếu một bên",
    "yếu tay chân bên phải đột ngột",
    "yếu tay chân",
    "yếu tay",
    "yếu chân",
    "yếu mặt",
    "tê yếu chân",
    "tê yếu tay",
    "tê các đầu ngón tay",
    "tê đầu ngón tay",
    "tê chân",
    "tê nhẹ",
    "cứng cổ",
    "nhạy cảm ánh sáng",
    "phát ban tím",
    "phát ban xuất huyết",
    "nổi mề đay toàn thân",
    "nổi mẩn ngứa nhẹ",
    "mẩn đỏ",
    "ngứa nhẹ",
    "ngứa da tái phát",
    "mụn viêm kéo dài",
    "sưng môi",
    "sưng mặt",
    "sưng",
    "sưng quanh mắt",
    "sưng nóng đỏ",
    "sưng đỏ quanh móng",
    "sưng đỏ",
    "sưng chân một bên",
    "sưng chân",
    "biến dạng",
    "đỏ lan",
    "đỏ nóng",
    "có mủ",
    "chảy mủ tai",
    "chảy máu nhiều",
    "chảy máu không cầm",
    "bầm tím lớn",
    "bầm tím",
    "lan nhanh",
    "vết thương đỏ",
    "vết cắt",
    "bỏng rộng",
    "phồng rộp",
    "điện giật",
    "uống nhầm hóa chất",
    "uống nhiều thuốc ngủ",
    "hóa chất bắn vào mắt",
    "hóa chất",
    "tai nạn xe máy",
    "chấn thương đầu",
    "ngã cao",
    "bụng cứng",
    "da lạnh",
    "vã mồ hôi lạnh",
    "hồi hộp từng cơn",
    "hồi hộp",
    "huyết áp cao",
    "tiểu buốt",
    "tiểu rát",
    "tiểu nhiều lần",
    "tiểu ra máu",
    "tiểu đêm nhiều lần",
    "bí tiểu",
    "không kiểm soát được tiểu tiện",
    "ra máu âm đạo",
    "ra máu quá nhiều",
    "kinh nguyệt không đều",
    "khí hư hôi",
    "đau khi quan hệ",
    "trễ kinh",
    "thai máy bất thường",
    "nuốt nghẹn",
    "khó nuốt nước bọt",
    "chảy nước dãi",
    "nhìn mờ",
    "giảm thị lực",
    "nghe kém",
    "ù tai",
    "khô mắt",
    "cộm mắt",
    "rụng tóc nhiều",
    "mất ngủ",
    "khó tập trung",
    "ý nghĩ tự làm hại bản thân",
    "chuột rút bắp chân",
    "đau cơ nhẹ",
)

SORTED_SYMPTOM_TERMS = sorted(set(SYMPTOM_TERMS), key=len, reverse=True)


def parse_symptoms(text: str) -> ParsedClinicalInfo:
    """Parse Vietnamese free-text symptoms into structured fields."""

    normalized = _normalize_text(text)
    negated_symptoms = _extract_negated_symptoms(normalized, SORTED_SYMPTOM_TERMS)
    symptoms = _extract_positive_symptoms(normalized, SORTED_SYMPTOM_TERMS, negated_symptoms)

    return ParsedClinicalInfo(
        symptoms=symptoms,
        negated_symptoms=negated_symptoms,
        duration=_extract_duration(normalized),
        severity=_extract_severity(normalized),
        vitals=_extract_vitals(normalized),
        risk_factors=_extract_risk_factors(normalized),
        raw_text=text,
    )


class SymptomParserAgent:
    """Thin agent wrapper around the deterministic parser."""

    def run(self, user_input: str) -> ParsedClinicalInfo:
        return parse_symptoms(user_input)


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("°c", " độ").replace("ºc", " độ")
    normalized = re.sub(r"[;:!?()\[\]{}]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _extract_positive_symptoms(
    text: str, vocabulary: Iterable[str], negated_symptoms: list[str]
) -> list[str]:
    found: list[str] = []
    for term in vocabulary:
        if term in negated_symptoms:
            continue
        if _contains_term(text, term) and not _is_negated_near_term(text, term):
            found.append(term)
    return _dedupe_specific_terms(found)


def _extract_negated_symptoms(text: str, vocabulary: Iterable[str]) -> list[str]:
    found: list[str] = []
    for term in vocabulary:
        if _contains_term(text, term) and _is_negated_near_term(text, term):
            found.append(term)
    return _dedupe_specific_terms(found)


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _is_negated_near_term(text: str, term: str) -> bool:
    for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text):
        prefix = text[max(0, match.start() - 28) : match.start()]
        if any(marker in prefix.split(",")[-1] for marker in NEGATION_MARKERS):
            return True
    return False


def _extract_duration(text: str) -> str | None:
    patterns = (
        r"(gần\s+)?\d+\s*(?:ngày|tuần|tháng|năm|giờ)",
        r"(?:từ\s+)?(?:sáng nay|tối qua|hôm qua|hôm nay)",
        r"nhiều\s+(?:ngày|tuần|tháng)",
        r"vài\s+(?:ngày|tuần|tháng)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
    return None


def _extract_severity(text: str) -> list[str]:
    return [term for term in SEVERITY_TERMS if term in text]


def _extract_vitals(text: str) -> dict[str, object]:
    vitals: dict[str, object] = {}

    bp_match = re.search(r"huyết áp\D{0,20}(\d{2,3})\s*/\s*(\d{2,3})", text)
    if bp_match:
        vitals["blood_pressure"] = f"{bp_match.group(1)}/{bp_match.group(2)}"

    spo2_match = re.search(r"spo2\D{0,12}(\d{2,3})\s*%?", text)
    if spo2_match:
        vitals["spo2"] = int(spo2_match.group(1))

    temp_patterns = (
        r"(?:sốt|nhiệt độ)\D{0,12}(\d{2}(?:[\.,]\d)?)\s*(?:độ|c\b)",
        r"nhiệt độ\D{0,12}(\d{2}(?:[\.,]\d)?)",
        r"(\d{2}(?:[\.,]\d)?)\s*(?:độ|c\b)",
    )
    for pattern in temp_patterns:
        temp_match = re.search(pattern, text)
        if temp_match:
            vitals["temperature"] = float(temp_match.group(1).replace(",", "."))
            break

    return vitals


def _extract_risk_factors(text: str) -> list[str]:
    risk_factors: list[str] = []
    for label, terms in RISK_FACTOR_TERMS.items():
        if any(term in text for term in terms):
            risk_factors.append(label)
    return risk_factors


def _dedupe_specific_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    for term in terms:
        if any(term != other and term in other for other in terms):
            continue
        if term not in result:
            result.append(term)
    return result
