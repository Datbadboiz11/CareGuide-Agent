from careguide.agents.answer import AnswerAgent, generate_answer, prefer_answerable_chunks
from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.red_flags import RedFlagFinding, RedFlagResult
from careguide.schemas.retrieval import RetrievalHit, RetrievalResult
from careguide.schemas.triage import TriageResult


def _parsed() -> ParsedClinicalInfo:
    return ParsedClinicalInfo(
        symptoms=["đau ngực", "khó thở"],
        negated_symptoms=["ngất"],
        duration="30 phút",
        severity=["nặng"],
        vitals={},
        risk_factors=[],
        raw_text="Tôi bị đau ngực và khó thở 30 phút, không ngất.",
    )


def _retrieval() -> RetrievalResult:
    hit = RetrievalHit(
        rank=1,
        chunk_id="nhs_chest_pain__section_0__chunk_0",
        document_id="nhs_chest_pain",
        source="NHS",
        url="https://www.nhs.uk/symptoms/chest-pain/",
        title="Chest pain",
        topic="chest pain",
        section_heading="Call 999 if:",
        section_type="immediate_action",
        text="Call 999 if chest pain does not go away or comes with shortness of breath.",
        final_score=0.02,
        vector_rank=1,
        bm25_rank=1,
        vector_score=0.8,
        bm25_score=20.0,
        section_bonus=0.004,
    )
    return RetrievalResult(
        query="Tôi bị đau ngực và khó thở",
        expanded_query="Tôi bị đau ngực và khó thở chest pain shortness of breath",
        mode="hybrid",
        top_k=5,
        vector_top_k=30,
        bm25_top_k=30,
        results=[hit],
    )


def _hit(rank: int, section_type: str, title: str = "Chest pain") -> RetrievalHit:
    return RetrievalHit(
        rank=rank,
        chunk_id=f"chunk_{rank}",
        document_id=f"doc_{rank}",
        source="NHS",
        url=f"https://www.nhs.uk/example/{rank}/",
        title=title,
        topic=title.lower(),
        section_heading="Summary",
        section_type=section_type,
        text=f"{title} {section_type} text",
        final_score=0.01,
    )


def test_generate_emergency_answer_has_safety_and_citations() -> None:
    triage = TriageResult(
        triage_level="emergency",
        confidence="high",
        main_reasons=["Đau ngực kèm khó thở là dấu hiệu nguy hiểm."],
        red_flags=["đau ngực kèm khó thở"],
        missing_info=[],
        recommended_action="Cần gọi cấp cứu hoặc đến cơ sở y tế gần nhất ngay.",
        requires_urgent=True,
        requires_emergency=True,
    )
    red_flags = RedFlagResult(
        red_flags=[
            RedFlagFinding(
                name="đau ngực kèm khó thở",
                severity="emergency",
                source="rule",
                evidence="đau ngực và khó thở",
                canonical="chest pain",
                reason="Có thể liên quan tình trạng cần cấp cứu.",
            )
        ],
        highest_severity="emergency",
        requires_urgent=True,
        requires_emergency=True,
    )

    answer = generate_answer(_parsed(), triage, red_flags, _retrieval())

    assert answer.triage_level == "emergency"
    assert "cấp cứu" in answer.recommendation.lower()
    assert answer.citations[0].source == "NHS"
    assert answer.citations[0].title == "Chest pain"
    assert "không thay thế chẩn đoán" in answer.safety_disclaimer
    assert answer.related_health_topics == ["Chest pain"]


def test_prefer_answerable_chunks_filters_metadata_when_enough_content_chunks() -> None:
    hits = [
        _hit(1, "urgent_advice"),
        _hit(2, "metadata"),
        _hit(3, "immediate_action", "Stomach ache"),
        _hit(4, "aliases"),
        _hit(5, "symptoms", "Abdominal Pain"),
    ]

    filtered = prefer_answerable_chunks(hits)

    assert [hit.section_type for hit in filtered] == ["urgent_advice", "immediate_action", "symptoms"]


def test_prefer_answerable_chunks_moves_low_value_chunks_to_the_end_when_content_is_limited() -> None:
    hits = [
        _hit(1, "urgent_advice"),
        _hit(2, "metadata"),
        _hit(3, "aliases"),
    ]

    filtered = prefer_answerable_chunks(hits)

    assert [hit.section_type for hit in filtered] == ["urgent_advice", "metadata", "aliases"]


def test_answer_agent_self_care_template() -> None:
    parsed = ParsedClinicalInfo(
        symptoms=["đau họng nhẹ"],
        negated_symptoms=["khó thở"],
        duration="1 ngày",
        severity=["nhẹ"],
        vitals={},
        risk_factors=[],
        raw_text="Tôi đau họng nhẹ 1 ngày, không khó thở.",
    )
    triage = TriageResult(
        triage_level="self_care",
        confidence="medium",
        main_reasons=["Triệu chứng nhẹ và chưa ghi nhận dấu hiệu nguy hiểm."],
        red_flags=[],
        missing_info=[],
        recommended_action="Có thể theo dõi tại nhà trong 24-48 giờ.",
        requires_urgent=False,
        requires_emergency=False,
    )
    red_flags = RedFlagResult()
    retrieval = RetrievalResult(
        query="đau họng nhẹ",
        mode="hybrid",
        top_k=5,
        vector_top_k=0,
        bm25_top_k=0,
        results=[],
    )

    answer = AnswerAgent().run(parsed, triage, red_flags, retrieval)

    assert answer.triage_level == "self_care"
    assert answer.citations == []
    assert any("Nghỉ ngơi" in advice for advice in answer.care_advice)
    assert "theo dõi" in answer.when_to_seek_help
