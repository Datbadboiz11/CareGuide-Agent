from __future__ import annotations

import argparse
import json
from pathlib import Path

from careguide.schemas.answer import AnswerCitation, CareGuideAnswer
from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.retrieval import RetrievalHit, RetrievalResult
from careguide.schemas.triage import TriageResult


MAX_CITATIONS = 5
MIN_ANSWERABLE_CHUNKS = 3
LOW_VALUE_SECTION_TYPES = {"metadata", "aliases"}
SAFETY_DISCLAIMER = (
    "Thông tin này chỉ hỗ trợ sàng lọc ban đầu và lập kế hoạch chăm sóc, "
    "không thay thế chẩn đoán hoặc điều trị của bác sĩ."
)


class AnswerAgent:

    def run(
        self,
        parsed: ParsedClinicalInfo,
        triage: TriageResult,
        red_flags: RedFlagResult,
        retrieval: RetrievalResult,
    ) -> CareGuideAnswer:
        return generate_answer(parsed, triage, red_flags, retrieval)


def generate_answer(
    parsed: ParsedClinicalInfo,
    triage: TriageResult,
    red_flags: RedFlagResult,
    retrieval: RetrievalResult,
) -> CareGuideAnswer:
    answer_hits = prefer_answerable_chunks(retrieval.results)
    return CareGuideAnswer(
        triage_level=triage.triage_level,
        confidence=triage.confidence,
        user_summary=build_user_summary(parsed),
        recommendation=build_recommendation(triage),
        care_advice=build_care_advice(triage),
        red_flags=build_red_flags(triage, red_flags),
        when_to_seek_help=build_when_to_seek_help(triage),
        possible_related_conditions=extract_related_conditions(answer_hits),
        citations=build_citations(answer_hits),
        safety_disclaimer=SAFETY_DISCLAIMER,
    )


def prefer_answerable_chunks(hits: list[RetrievalHit], minimum_answerable: int = MIN_ANSWERABLE_CHUNKS) -> list[RetrievalHit]:
    answerable = [hit for hit in hits if hit.section_type not in LOW_VALUE_SECTION_TYPES]
    if len(answerable) >= minimum_answerable:
        return answerable
    low_value = [hit for hit in hits if hit.section_type in LOW_VALUE_SECTION_TYPES]
    return answerable + low_value


def build_user_summary(parsed: ParsedClinicalInfo) -> str:
    parts: list[str] = []
    if parsed.symptoms:
        parts.append(f"Triệu chứng bạn mô tả: {', '.join(parsed.symptoms)}.")
    else:
        parts.append("Bạn đã mô tả một vấn đề sức khỏe cần được sàng lọc.")

    if parsed.duration:
        parts.append(f"Thời gian: {parsed.duration}.")
    if parsed.severity:
        parts.append(f"Mức độ/xu hướng: {', '.join(parsed.severity)}.")
    if parsed.vitals:
        vitals = ", ".join(f"{key}: {value}" for key, value in parsed.vitals.items())
        parts.append(f"Chỉ số ghi nhận: {vitals}.")
    if parsed.negated_symptoms:
        parts.append(f"Bạn cũng nói không có: {', '.join(parsed.negated_symptoms)}.")

    return " ".join(parts)


def build_recommendation(triage: TriageResult) -> str:
    labels = {
        "emergency": "Cần xử trí cấp cứu.",
        "urgent_visit": "Nên đi khám sớm.",
        "routine_visit": "Nên đặt lịch khám thường quy.",
        "self_care": "Có thể chăm sóc và theo dõi tại nhà nếu không có dấu hiệu nặng lên.",
    }
    prefix = labels[triage.triage_level]
    return f"{prefix} {triage.recommended_action}"


def build_care_advice(triage: TriageResult) -> list[str]:
    if triage.triage_level == "emergency":
        return [
            "Gọi cấp cứu hoặc đến cơ sở y tế gần nhất ngay.",
            "Không tự lái xe nếu có đau ngực nặng, khó thở nhiều, ngất, yếu liệt hoặc lú lẫn.",
            "Chuẩn bị thông tin về triệu chứng, thời điểm bắt đầu, bệnh nền và thuốc đang dùng.",
        ]

    if triage.triage_level == "urgent_visit":
        return [
            "Sắp xếp đi khám trong thời gian sớm, đặc biệt nếu triệu chứng đang nặng lên.",
            "Theo dõi nhiệt độ, nhịp thở, SpO2, huyết áp hoặc nhịp tim nếu có thiết bị đo.",
            "Tránh tự dùng thuốc mạnh hoặc kháng sinh khi chưa được nhân viên y tế hướng dẫn.",
        ]

    if triage.triage_level == "routine_visit":
        return [
            "Đặt lịch khám để được đánh giá nguyên nhân và kế hoạch chăm sóc phù hợp.",
            "Ghi lại triệu chứng, thời điểm xuất hiện, yếu tố làm nặng/giảm và thuốc đã dùng.",
            "Đi khám sớm hơn nếu xuất hiện dấu hiệu cảnh báo hoặc triệu chứng tiến triển nhanh.",
        ]

    return [
        "Nghỉ ngơi, uống đủ nước và theo dõi triệu chứng trong 24-48 giờ.",
        "Có thể dùng các biện pháp chăm sóc thông thường phù hợp với triệu chứng nhẹ.",
        "Đi khám nếu triệu chứng kéo dài, tái diễn, nặng lên hoặc làm bạn lo lắng.",
    ]


def build_red_flags(triage: TriageResult, red_flags: RedFlagResult) -> list[str]:
    flags = list(triage.red_flags)
    flags.extend(finding.name for finding in red_flags.red_flags)
    return _dedupe(flags)


def build_when_to_seek_help(triage: TriageResult) -> str:
    if triage.triage_level == "emergency":
        return "Tìm trợ giúp y tế khẩn cấp ngay bây giờ."
    if triage.triage_level == "urgent_visit":
        return "Đi khám sớm, và chuyển sang cấp cứu nếu có khó thở nặng, đau ngực nặng, ngất, lú lẫn, yếu liệt hoặc triệu chứng xấu đi nhanh."
    if triage.triage_level == "routine_visit":
        return "Đặt lịch khám; đi khám sớm hơn nếu xuất hiện sốt cao, đau tăng, khó thở, mất nước, chảy máu hoặc triệu chứng mới đáng lo."
    return "Tiếp tục theo dõi; đi khám nếu triệu chứng không cải thiện, kéo dài, tái diễn hoặc xuất hiện dấu hiệu cảnh báo."


def extract_related_conditions(hits: list[RetrievalHit], limit: int = 5) -> list[str]:
    candidates: list[str] = []
    for hit in hits:
        title = hit.title.strip()
        if title and title.lower() not in {"symptoms", "overview"}:
            candidates.append(title)
    return _dedupe(candidates)[:limit]


def build_citations(hits: list[RetrievalHit]) -> list[AnswerCitation]:
    citations: list[AnswerCitation] = []
    seen: set[tuple[str, str, str]] = set()

    for hit in hits:
        key = (hit.source, hit.title, str(hit.url))
        if key in seen:
            continue
        citations.append(
            AnswerCitation(
                source=hit.source,
                title=hit.title,
                url=hit.url,
                chunk_id=hit.chunk_id,
                section_heading=hit.section_heading,
                section_type=hit.section_type,
            )
        )
        seen.add(key)
        if len(citations) >= MAX_CITATIONS:
            break

    return citations


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    answer = generate_answer(
        parsed=ParsedClinicalInfo.model_validate(payload["parsed"]),
        triage=TriageResult.model_validate(payload["triage"]),
        red_flags=RedFlagResult.model_validate(payload["red_flags"]),
        retrieval=RetrievalResult.model_validate(payload["retrieval"]),
    )
    print(json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
