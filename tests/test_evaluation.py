from careguide.evaluation.answer_eval import aggregate_answer_metrics, evaluate_answer, load_cases as load_answer_cases
from careguide.evaluation.e2e_eval import (
    E2EEvalCase,
    aggregate_e2e_metrics,
    evaluate_e2e_result,
    load_cases as load_e2e_cases,
    write_report,
)
from careguide.evaluation.retrieval_eval import (
    RetrievalEvalCase,
    aggregate_retrieval_metrics,
    evaluate_retrieval_result,
    first_matching_rank,
    load_cases as load_retrieval_cases,
)
from careguide.schemas.answer import AnswerCitation, CareGuideAnswer
from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import NormalizationResult, NormalizedSymptom
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.retrieval import RetrievalHit, RetrievalResult
from careguide.schemas.triage import TriageResult


def _hit(rank: int, title: str, source: str, section_type: str) -> RetrievalHit:
    return RetrievalHit(
        rank=rank,
        chunk_id=f"chunk_{rank}",
        document_id=f"doc_{rank}",
        source=source,
        url=f"https://example.com/{rank}",
        title=title,
        topic=title.lower(),
        section_heading="Summary",
        section_type=section_type,
        text=f"{title} text",
        final_score=0.01,
    )


def test_first_matching_rank() -> None:
    assert first_matching_rank(["Flu", "Chest pain"], ["Chest pain"]) == 2
    assert first_matching_rank(["Flu"], ["Stroke"]) is None


def test_evaluate_retrieval_result_computes_hits_and_mrr() -> None:
    case = RetrievalEvalCase(
        id="case_1",
        query="đau ngực",
        expanded_terms=["chest pain"],
        expected_titles_any=["Chest pain"],
        expected_sources_any=["NHS"],
        expected_section_types_any=["immediate_action"],
    )
    result = RetrievalResult(
        query="đau ngực",
        mode="hybrid",
        top_k=5,
        vector_top_k=2,
        bm25_top_k=2,
        results=[
            _hit(1, "Flu", "CDC", "symptoms"),
            _hit(2, "Chest pain", "NHS", "immediate_action"),
        ],
    )

    detail = evaluate_retrieval_result(case, result)

    assert detail["hit_title"] is True
    assert detail["title_rank"] == 2
    assert detail["mrr_title"] == 0.5
    assert detail["hit_source"] is True
    assert detail["hit_section_type"] is True
    assert detail["answerable_chunks_at_5"] == 2
    assert detail["low_value_section_rate_at_5"] == 0.0


def test_evaluate_retrieval_result_tracks_low_value_sections() -> None:
    case = RetrievalEvalCase(
        id="case_2",
        query="đau bụng",
        expanded_terms=["abdominal pain"],
        expected_titles_any=["Abdominal Pain"],
        expected_sources_any=["MedlinePlus"],
        expected_section_types_any=["urgent_advice"],
    )
    result = RetrievalResult(
        query="đau bụng",
        mode="hybrid",
        top_k=5,
        vector_top_k=2,
        bm25_top_k=2,
        results=[
            _hit(1, "Abdominal Pain", "MedlinePlus", "urgent_advice"),
            _hit(2, "Abdominal Pain", "MedlinePlus", "metadata"),
            _hit(3, "Abdominal Pain", "MedlinePlus", "aliases"),
        ],
    )

    detail = evaluate_retrieval_result(case, result)

    assert detail["answerable_chunks_at_5"] == 1
    assert detail["low_value_section_rate_at_5"] == 2 / 3


def test_aggregate_retrieval_metrics() -> None:
    metrics = aggregate_retrieval_metrics(
        [
            {
                "hit_title": True,
                "hit_source": True,
                "hit_section_type": True,
                "mrr_title": 1.0,
                "top_score": 0.1,
                "answerable_chunks_at_5": 5,
                "low_value_section_rate_at_5": 0.0,
            },
            {
                "hit_title": False,
                "hit_source": True,
                "hit_section_type": False,
                "mrr_title": 0.0,
                "top_score": 0.2,
                "answerable_chunks_at_5": 3,
                "low_value_section_rate_at_5": 0.4,
            },
        ]
    )

    assert metrics["hit_at_5_title"] == 0.5
    assert metrics["hit_at_5_source"] == 1.0
    assert metrics["mrr_title"] == 0.5
    assert metrics["avg_answerable_chunks_at_5"] == 4.0
    assert metrics["avg_low_value_section_rate_at_5"] == 0.2


def test_answer_eval_case_files_load() -> None:
    cases = load_answer_cases("data/test_cases/answer_eval_cases.jsonl")

    assert len(cases) >= 3
    assert cases[0].expected_triage_level in {"self_care", "routine_visit", "urgent_visit", "emergency"}


def test_retrieval_eval_case_files_load() -> None:
    cases = load_retrieval_cases("data/test_cases/retrieval_eval_cases.jsonl")

    assert len(cases) >= 5
    assert all(case.expected_titles_any for case in cases)


def test_e2e_eval_case_files_load() -> None:
    cases = load_e2e_cases("data/test_cases/e2e_eval_cases.jsonl")

    assert len(cases) >= 20
    assert all(case.expected_retrieval_titles_any for case in cases)


def test_evaluate_e2e_result_classifies_pass() -> None:
    case = E2EEvalCase(
        id="e2e_case_1",
        input="Tôi bị đau ngực và khó thở",
        expected_triage_level="emergency",
        expected_symptoms_any=["đau ngực"],
        expected_expanded_terms_any=["chest pain"],
        expected_retrieval_titles_any=["Chest pain"],
        expected_section_types_any=["immediate_action"],
        min_answerable_chunks=1,
        must_include=["cấp cứu"],
        must_not_include=["chẩn đoán là"],
        requires_citation=True,
        requires_disclaimer=True,
        requires_safe_escalation=True,
    )
    state = _e2e_state()

    detail = evaluate_e2e_result(case, state)

    assert detail["passed"] is True
    assert detail["failure_stage"] is None
    assert detail["checks"]["parser_symptom_hit"] is True
    assert detail["checks"]["retrieval_hit_at_5_title"] is True
    assert detail["checks"]["safety_pass"] is True


def test_evaluate_e2e_result_classifies_retrieval_error() -> None:
    case = E2EEvalCase(
        id="e2e_case_2",
        input="Tôi bị đau ngực và khó thở",
        expected_triage_level="emergency",
        expected_symptoms_any=["đau ngực"],
        expected_expanded_terms_any=["chest pain"],
        expected_retrieval_titles_any=["Stroke"],
        expected_section_types_any=["immediate_action"],
        min_answerable_chunks=1,
        must_include=["cấp cứu"],
        requires_citation=True,
        requires_disclaimer=True,
        requires_safe_escalation=True,
    )

    detail = evaluate_e2e_result(case, _e2e_state())

    assert detail["passed"] is False
    assert detail["failure_stage"] == "retrieval_error"


def test_aggregate_e2e_metrics_and_write_report(tmp_path) -> None:
    metrics = aggregate_e2e_metrics(
        [
            {
                "passed": True,
                "failure_stage": None,
                "checks": {
                    "parser_symptom_hit": True,
                    "normalizer_expansion_hit": True,
                    "triage_correct": True,
                    "retrieval_hit_at_5_title": True,
                    "retrieval_hit_at_5_section_type": True,
                    "answer_context_has_expected_title": True,
                    "min_answerable_chunks_pass": True,
                    "citation_requirement_pass": True,
                    "disclaimer_requirement_pass": True,
                    "safe_escalation_pass": True,
                    "must_include_pass": True,
                    "must_include_any_pass": True,
                    "must_not_include_pass": True,
                    "safety_pass": True,
                },
            },
            {
                "passed": False,
                "failure_stage": "retrieval_error",
                "checks": {
                    "parser_symptom_hit": True,
                    "normalizer_expansion_hit": True,
                    "triage_correct": True,
                    "retrieval_hit_at_5_title": False,
                    "retrieval_hit_at_5_section_type": True,
                    "answer_context_has_expected_title": False,
                    "min_answerable_chunks_pass": True,
                    "citation_requirement_pass": True,
                    "disclaimer_requirement_pass": True,
                    "safe_escalation_pass": True,
                    "must_include_pass": True,
                    "must_include_any_pass": True,
                    "must_not_include_pass": True,
                    "safety_pass": True,
                },
            },
        ]
    )
    report_path = tmp_path / "e2e_eval_report.json"
    failures_path = tmp_path / "e2e_failures.jsonl"

    write_report(metrics, report_path, failures_path)

    assert metrics["passed_rate"] == 0.5
    assert metrics["failure_stage_counts"] == {"retrieval_error": 1}
    assert report_path.exists()
    assert failures_path.read_text(encoding="utf-8").count("\n") == 1


def test_evaluate_answer_rules() -> None:
    case = load_answer_cases("data/test_cases/answer_eval_cases.jsonl")[0]
    answer = {
        "triage_level": "emergency",
        "recommendation": "Cần gọi cấp cứu vì đau ngực và khó thở.",
        "care_advice": ["Gọi cấp cứu ngay."],
        "citations": [{"source": "NHS"}],
        "safety_disclaimer": "Không thay thế chẩn đoán của bác sĩ.",
    }

    detail = evaluate_answer(case, answer)

    assert detail["triage_correct"] is True
    assert detail["citation_present"] is True
    assert detail["citation_requirement_pass"] is True
    assert detail["disclaimer_present"] is True
    assert detail["disclaimer_requirement_pass"] is True
    assert detail["must_include_pass"] is True
    assert detail["must_not_include_pass"] is True


def test_evaluate_answer_tracks_optional_citation_separately() -> None:
    case = load_answer_cases("data/test_cases/answer_eval_cases.jsonl")[2]
    answer = {
        "triage_level": "self_care",
        "recommendation": "Theo dÃµi táº¡i nhÃ  trong 24-48 giá».",
        "care_advice": ["Nghá»‰ ngÆ¡i vÃ  theo dÃµi."],
        "citations": [],
        "safety_disclaimer": "KhÃ´ng thay tháº¿ cháº©n Ä‘oÃ¡n cá»§a bÃ¡c sÄ©.",
    }

    detail = evaluate_answer(case, answer)

    assert detail["citation_present"] is False
    assert detail["citation_requirement_pass"] is True
    assert detail["citation_count"] == 0


def test_aggregate_answer_metrics() -> None:
    metrics = aggregate_answer_metrics(
        [
            {
                "triage_correct": True,
                "citation_present": True,
                "citation_requirement_pass": True,
                "disclaimer_present": True,
                "disclaimer_requirement_pass": True,
                "must_include_pass": True,
                "must_not_include_pass": True,
                "safe_escalation_pass": True,
            },
            {
                "triage_correct": False,
                "citation_present": False,
                "citation_requirement_pass": True,
                "disclaimer_present": True,
                "disclaimer_requirement_pass": True,
                "must_include_pass": False,
                "must_not_include_pass": True,
                "safe_escalation_pass": True,
            },
        ]
    )

    assert metrics["triage_accuracy"] == 0.5
    assert metrics["citation_present_rate"] == 0.5
    assert metrics["citation_requirement_pass_rate"] == 1.0
    assert metrics["must_include_pass_rate"] == 0.5


def _e2e_state() -> dict:
    hit = _hit(1, "Chest pain", "NHS", "immediate_action")
    citation = AnswerCitation(
        source="NHS",
        title="Chest pain",
        url="https://example.com/1",
        chunk_id="chunk_1",
        section_heading="Call 999 if:",
        section_type="immediate_action",
    )
    answer = CareGuideAnswer(
        triage_level="emergency",
        confidence="high",
        user_summary="Triệu chứng bạn mô tả: đau ngực, khó thở.",
        recommendation="Cần gọi cấp cứu ngay.",
        care_advice=["Gọi cấp cứu hoặc đến cơ sở y tế gần nhất."],
        red_flags=["Chest pain with shortness of breath"],
        when_to_seek_help="Tìm trợ giúp y tế khẩn cấp ngay bây giờ.",
        related_health_topics=["Chest pain"],
        citations=[citation],
        safety_disclaimer="Thông tin này không thay thế chẩn đoán hoặc điều trị của bác sĩ.",
    )
    return {
        "raw_input": "Tôi bị đau ngực và khó thở",
        "errors": [],
        "parsed": ParsedClinicalInfo(
            symptoms=["đau ngực", "khó thở"],
            raw_text="Tôi bị đau ngực và khó thở",
        ),
        "normalized": NormalizationResult(
            normalized_symptoms=[
                NormalizedSymptom(
                    original="đau ngực",
                    canonical="chest pain",
                    category="cardiovascular",
                    confidence=1.0,
                    matched_alias="đau ngực",
                    red_flag_hint=True,
                )
            ]
        ),
        "red_flags": RedFlagResult(requires_urgent=True, requires_emergency=True),
        "triage": TriageResult(
            triage_level="emergency",
            confidence="high",
            recommended_action="Cần gọi cấp cứu ngay.",
            requires_urgent=True,
            requires_emergency=True,
        ),
        "retrieval_query": "Tôi bị đau ngực và khó thở",
        "expanded_terms": ["chest pain", "shortness of breath"],
        "retrieval": RetrievalResult(
            query="Tôi bị đau ngực và khó thở",
            mode="hybrid",
            top_k=5,
            vector_top_k=1,
            bm25_top_k=1,
            results=[hit],
        ),
        "answer_context": [hit],
        "answer": answer,
        "safety": {
            "requires_citation": True,
            "passed": True,
            "checks": {
                "no_definitive_diagnosis": True,
                "no_prescribing_or_dosage": True,
                "emergency_escalation_present": True,
                "disclaimer_present": True,
                "citation_requirement_pass": True,
            },
        },
        "final_output": {
            "triage_level": answer.triage_level,
            "confidence": answer.confidence,
            "user_summary": answer.user_summary,
            "recommendation": answer.recommendation,
            "care_advice": answer.care_advice,
            "red_flags": answer.red_flags,
            "when_to_seek_help": answer.when_to_seek_help,
            "related_health_topics": answer.related_health_topics,
            "citations": [citation.model_dump(mode="json")],
            "safety_disclaimer": answer.safety_disclaimer,
            "safety": {
                "requires_citation": True,
                "passed": True,
            },
        },
    }
