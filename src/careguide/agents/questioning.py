from __future__ import annotations

from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import NormalizationResult
from careguide.schemas.questioning import FollowUpQuestion, QuestioningResult
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.triage import TriageResult


MAX_QUESTIONS = 5


class QuestioningAgent:

    def run(
        self,
        parsed: ParsedClinicalInfo,
        normalized: NormalizationResult,
        red_flags: RedFlagResult,
        triage: TriageResult,
    ) -> QuestioningResult:
        return generate_followup_questions(parsed, normalized, red_flags, triage)


def generate_followup_questions(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
    red_flags: RedFlagResult,
    triage: TriageResult,
) -> QuestioningResult:
    if triage.requires_emergency or red_flags.requires_emergency:
        return QuestioningResult(
            should_ask=False,
            questions=[],
            skipped_reason="Có dấu hiệu cấp cứu, không nên trì hoãn để hỏi thêm.",
        )

    questions: list[FollowUpQuestion] = []
    canonicals = _positive_canonicals(normalized)

    _add_missing_info_questions(questions, parsed, triage)
    _add_symptom_specific_questions(questions, canonicals)
    _add_risk_questions(questions, parsed, triage)

    questions = _dedupe_questions(questions)
    questions = _sort_questions(questions)
    limit = 3 if triage.triage_level == "urgent_visit" else MAX_QUESTIONS
    questions = questions[:limit]

    return QuestioningResult(
        should_ask=bool(questions),
        questions=questions,
        skipped_reason=None if questions else "Không có câu hỏi bổ sung quan trọng ở bước này.",
    )


def _add_missing_info_questions(
    questions: list[FollowUpQuestion],
    parsed: ParsedClinicalInfo,
    triage: TriageResult,
) -> None:
    missing = set(triage.missing_info)

    if "tuổi" in missing:
        questions.append(
            _question(
                "Bạn bao nhiêu tuổi?",
                "Tuổi ảnh hưởng đến mức độ rủi ro và khuyến nghị chăm sóc.",
                "high" if triage.triage_level == "urgent_visit" else "medium",
                "age",
            )
        )

    if "thời gian triệu chứng" in missing:
        questions.append(
            _question(
                "Triệu chứng bắt đầu từ khi nào và có đang nặng lên không?",
                "Thời gian và xu hướng nặng lên ảnh hưởng trực tiếp đến phân loại chăm sóc.",
                "high",
                "duration",
            )
        )

    if "bệnh nền/thuốc đang dùng" in missing:
        questions.append(
            _question(
                "Bạn có bệnh nền, đang mang thai hoặc đang dùng thuốc gì không?",
                "Bệnh nền, thai kỳ và thuốc đang dùng có thể làm tăng rủi ro.",
                "high" if triage.triage_level == "urgent_visit" else "medium",
                "risk_factor",
            )
        )

    if not parsed.vitals and triage.triage_level in {"urgent_visit", "routine_visit"}:
        questions.append(
            _question(
                "Bạn có đo được nhiệt độ, SpO2, huyết áp hoặc nhịp tim không?",
                "Chỉ số sinh tồn giúp đánh giá mức độ cần đi khám.",
                "medium",
                "vitals",
            )
        )


def _add_symptom_specific_questions(
    questions: list[FollowUpQuestion],
    canonicals: set[str],
) -> None:
    if canonicals & {"cough", "dry cough", "productive cough", "fever", "sore throat"}:
        questions.append(
            _question(
                "Bạn có khó thở, đau ngực, SpO2 thấp, ho ra máu hoặc sốt cao kéo dài không?",
                "Đây là các dấu hiệu nguy hiểm liên quan đến triệu chứng hô hấp/sốt.",
                "high",
                "respiratory_red_flags",
            )
        )

    if "abdominal pain" in canonicals or "epigastric pain" in canonicals:
        questions.append(
            _question(
                "Bạn đau ở vị trí nào, mức độ đau 0-10, có sốt, nôn ra máu hoặc đi ngoài phân đen không?",
                "Vị trí đau và dấu hiệu xuất huyết/sốt giúp phân biệt mức độ khẩn.",
                "high",
                "abdominal_red_flags",
            )
        )

    if canonicals & {"headache", "dizziness"}:
        questions.append(
            _question(
                "Bạn có đau đầu đột ngột dữ dội, yếu liệt, nói khó, lơ mơ, ngất hoặc co giật không?",
                "Các dấu hiệu thần kinh này cần được phát hiện sớm.",
                "high",
                "neurologic_red_flags",
            )
        )

    if canonicals & {"chest pain", "palpitations"}:
        questions.append(
            _question(
                "Bạn có khó thở, vã mồ hôi lạnh, ngất, đau lan lên hàm/tay hoặc đau khi gắng sức không?",
                "Đau ngực/hồi hộp có thể liên quan đến tình huống cần đánh giá sớm.",
                "high",
                "cardiac_red_flags",
            )
        )

    if canonicals & {"rash", "hives", "itching", "lip swelling", "facial swelling"}:
        questions.append(
            _question(
                "Bạn có khó thở, sưng môi/mặt, chóng mặt hoặc nổi mề đay lan nhanh không?",
                "Đây là dấu hiệu phản ứng dị ứng nghiêm trọng.",
                "high",
                "allergy_red_flags",
            )
        )

    if canonicals & {"dysuria", "hematuria", "urinary frequency", "flank pain"}:
        questions.append(
            _question(
                "Bạn có sốt, đau hông lưng, nôn, tiểu ra máu hoặc đang mang thai không?",
                "Các dấu hiệu này làm triệu chứng tiết niệu cần được khám sớm hơn.",
                "high",
                "urinary_red_flags",
            )
        )

    if canonicals & {"back pain", "numbness", "weakness"}:
        questions.append(
            _question(
                "Bạn có tê yếu chân, bí tiểu, mất kiểm soát tiểu tiện hoặc đau sau chấn thương không?",
                "Đây là các dấu hiệu nguy hiểm liên quan đến lưng/cột sống.",
                "high",
                "spine_red_flags",
            )
        )

    if canonicals & {"vaginal bleeding", "missed period", "abdominal pain", "vaginal discharge"}:
        questions.append(
            _question(
                "Bạn có đang mang thai, trễ kinh, ra máu âm đạo, đau bụng tăng hoặc chóng mặt muốn ngất không?",
                "Thai kỳ hoặc ra máu kèm đau bụng có thể cần đánh giá khẩn.",
                "high",
                "pregnancy_gynecology",
            )
        )


def _add_risk_questions(
    questions: list[FollowUpQuestion],
    parsed: ParsedClinicalInfo,
    triage: TriageResult,
) -> None:
    if parsed.risk_factors:
        questions.append(
            _question(
                "Các bệnh nền hoặc yếu tố nguy cơ của bạn hiện có đang ổn định không?",
                "Yếu tố nguy cơ có thể làm mức khuyến nghị chăm sóc thay đổi.",
                "medium",
                "risk_factor_status",
            )
        )

    if triage.triage_level == "urgent_visit":
        questions.append(
            _question(
                "Hiện tại triệu chứng có đang nặng lên nhanh hoặc làm bạn khó sinh hoạt không?",
                "Tốc độ nặng lên giúp quyết định cần đi khám sớm hay cấp cứu.",
                "high",
                "progression",
            )
        )


def _question(
    text: str,
    reason: str,
    priority: str,
    topic: str,
) -> FollowUpQuestion:
    return FollowUpQuestion(
        question=text,
        reason=reason,
        priority=priority,
        topic=topic,
    )


def _positive_canonicals(normalized: NormalizationResult) -> set[str]:
    return {item.canonical for item in normalized.normalized_symptoms if not item.negated}


def _dedupe_questions(questions: list[FollowUpQuestion]) -> list[FollowUpQuestion]:
    result: list[FollowUpQuestion] = []
    seen_topics: set[str] = set()
    seen_text: set[str] = set()
    for question in questions:
        if question.topic in seen_topics or question.question in seen_text:
            continue
        result.append(question)
        seen_topics.add(question.topic)
        seen_text.add(question.question)
    return result


def _sort_questions(questions: list[FollowUpQuestion]) -> list[FollowUpQuestion]:
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(questions, key=lambda item: priority_rank[item.priority])

