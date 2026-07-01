from __future__ import annotations

import re

from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import NormalizationResult
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.triage import TriageResult


LONG_DURATION_MARKERS = (
    "tuần",
    "tháng",
    "năm",
    "hơn 10 ngày",
    "nhiều tuần",
    "nhiều tháng",
    "vài tuần",
    "vài tháng",
)

RECURRENT_MARKERS = (
    "tái diễn",
    "tái đi tái lại",
    "thường xuyên",
    "nhiều lần",
    "mỗi tuần",
)

URGENT_TEXT_MARKERS = (
    "tăng dần",
    "đau nhiều",
    "đau nhức tăng",
    "rất mệt",
    "mệt nhiều",
    "uống nước kém",
    "bỏ ăn",
    "khát nhiều",
    "đỏ lan",
    "có mủ",
    "nhìn hơi mờ",
    "nghe kém",
    "ho ra",
)

URGENT_CANONICALS = {
    "hemoptysis",
    "high blood pressure",
    "hematuria",
    "leg swelling",
    "localized swelling",
    "pus",
    "blurred vision",
    "difficulty swallowing",
    "photophobia",
    "bloody diarrhea",
    "poor hydration",
}

ROUTINE_CANONICALS = {
    "insomnia",
    "tinnitus",
    "irregular menstruation",
    "hair loss",
    "dyspareunia",
    "urinary frequency",
    "dry eyes",
    "acne",
}


class TriageAgent:

    def run(
        self,
        parsed: ParsedClinicalInfo,
        normalized: NormalizationResult,
        red_flags: RedFlagResult,
    ) -> TriageResult:
        return classify_triage(parsed, normalized, red_flags)


def classify_triage(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
    red_flags: RedFlagResult,
) -> TriageResult:
    if red_flags.requires_emergency:
        return _result(
            level="emergency",
            confidence="high",
            reasons=_red_flag_reasons(red_flags) or ["Có dấu hiệu nguy hiểm cần đánh giá khẩn cấp."],
            red_flags=red_flags,
            missing_info=[],
        )

    if _should_be_urgent(parsed, normalized, red_flags):
        return _result(
            level="urgent_visit",
            confidence="medium" if _missing_info(parsed) else "high",
            reasons=_urgent_reasons(parsed, normalized, red_flags),
            red_flags=red_flags,
            missing_info=_missing_info(parsed),
        )

    if _should_be_routine(parsed, normalized):
        return _result(
            level="routine_visit",
            confidence="medium",
            reasons=_routine_reasons(parsed, normalized),
            red_flags=red_flags,
            missing_info=_missing_info(parsed),
        )

    return _result(
        level="self_care",
        confidence="medium",
        reasons=["Triệu chứng có vẻ nhẹ/ngắn ngày và chưa ghi nhận dấu hiệu nguy hiểm."],
        red_flags=red_flags,
        missing_info=_missing_info(parsed),
    )


def _should_be_urgent(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
    red_flags: RedFlagResult,
) -> bool:
    if red_flags.requires_urgent:
        return True

    raw = parsed.raw_text.lower()
    canonicals = _positive_canonicals(normalized)

    temperature = parsed.vitals.get("temperature")
    if isinstance(temperature, (int, float)) and temperature >= 38.5 and _has_risk_factor(parsed):
        return True
    if isinstance(temperature, (int, float)) and temperature >= 39:
        return True

    if canonicals & URGENT_CANONICALS:
        return True
    if any(marker in raw for marker in URGENT_TEXT_MARKERS):
        return True
    if _has_risk_factor(parsed) and canonicals & {"fever", "cough", "shortness of breath", "abdominal pain", "wound redness"}:
        return True
    if "abdominal pain" in canonicals and "fever" in canonicals:
        return True
    if "dysuria" in canonicals and ("fever" in canonicals or "back pain" in canonicals):
        return True

    return False


def _should_be_routine(parsed: ParsedClinicalInfo, normalized: NormalizationResult) -> bool:
    raw = parsed.raw_text.lower()
    canonicals = _positive_canonicals(normalized)

    if parsed.duration and any(marker in parsed.duration for marker in LONG_DURATION_MARKERS):
        return True
    if any(marker in raw for marker in LONG_DURATION_MARKERS + RECURRENT_MARKERS):
        return True
    if canonicals & ROUTINE_CANONICALS:
        return True

    return False


def _urgent_reasons(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
    red_flags: RedFlagResult,
) -> list[str]:
    reasons = _red_flag_reasons(red_flags)
    raw = parsed.raw_text.lower()
    canonicals = _positive_canonicals(normalized)

    if _has_risk_factor(parsed):
        reasons.append("Có yếu tố nguy cơ cần thận trọng hơn.")
    if any(marker in raw for marker in URGENT_TEXT_MARKERS):
        reasons.append("Triệu chứng có dấu hiệu nặng hơn hoặc đáng lo.")
    if "abdominal pain" in canonicals and "fever" in canonicals:
        reasons.append("Đau bụng kèm sốt nên được đánh giá sớm.")
    if not reasons:
        reasons.append("Có dấu hiệu cần đi khám sớm để được đánh giá trực tiếp.")
    return _dedupe(reasons)


def _routine_reasons(parsed: ParsedClinicalInfo, normalized: NormalizationResult) -> list[str]:
    raw = parsed.raw_text.lower()
    reasons: list[str] = []

    if parsed.duration and any(marker in parsed.duration for marker in LONG_DURATION_MARKERS):
        reasons.append("Triệu chứng kéo dài nên đặt lịch khám.")
    if any(marker in raw for marker in RECURRENT_MARKERS):
        reasons.append("Triệu chứng tái diễn hoặc xuất hiện thường xuyên.")
    if _positive_canonicals(normalized) & ROUTINE_CANONICALS:
        reasons.append("Triệu chứng cần tư vấn chuyên môn nhưng chưa ghi nhận dấu hiệu cấp cứu.")
    if not reasons:
        reasons.append("Triệu chứng chưa cấp cứu nhưng nên được bác sĩ đánh giá theo lịch khám.")
    return _dedupe(reasons)


def _red_flag_reasons(red_flags: RedFlagResult) -> list[str]:
    return [finding.reason for finding in red_flags.red_flags]


def _result(
    level: str,
    confidence: str,
    reasons: list[str],
    red_flags: RedFlagResult,
    missing_info: list[str],
) -> TriageResult:
    return TriageResult(
        triage_level=level,
        confidence=confidence,
        main_reasons=_dedupe(reasons),
        red_flags=[finding.name for finding in red_flags.red_flags],
        missing_info=missing_info,
        recommended_action=_recommended_action(level),
        requires_urgent=level in {"urgent_visit", "emergency"},
        requires_emergency=level == "emergency",
    )


def _recommended_action(level: str) -> str:
    if level == "emergency":
        return "Cần gọi cấp cứu hoặc đến cơ sở y tế gần nhất ngay."
    if level == "urgent_visit":
        return "Nên đi khám sớm để được đánh giá trực tiếp."
    if level == "routine_visit":
        return "Nên đặt lịch khám để được tư vấn và kiểm tra."
    return "Có thể theo dõi tại nhà trong 24-48 giờ nếu triệu chứng không nặng lên."


def _positive_canonicals(normalized: NormalizationResult) -> set[str]:
    return {item.canonical for item in normalized.normalized_symptoms if not item.negated}


def _has_risk_factor(parsed: ParsedClinicalInfo) -> bool:
    return bool(parsed.risk_factors)


def _missing_info(parsed: ParsedClinicalInfo) -> list[str]:
    raw = parsed.raw_text.lower()
    missing: list[str] = []

    if re.search(r"\b\d{1,3}\s*(tuổi|tháng)\b", raw) is None and not any(
        marker in raw for marker in ("mang thai", "trẻ", "em bé", "người già")
    ):
        missing.append("tuổi")
    if not parsed.duration:
        missing.append("thời gian triệu chứng")
    if not any(marker in raw for marker in ("bệnh nền", "tiểu đường", "hen", "thuốc", "mang thai")):
        missing.append("bệnh nền/thuốc đang dùng")

    return missing[:3]


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
