from __future__ import annotations

from typing import Any

from careguide.graph.careguide_graph import CareGuideGraph, select_answer_context
from careguide.schemas.retrieval import RetrievalHit, RetrievalResult


class FakeRetriever:

    def __init__(self, results: list[RetrievalHit]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def run(
        self,
        query: str,
        expanded_terms: list[str] | None = None,
        top_k: int = 5,
        mode: str = "hybrid",
        vector_top_k: int = 30,
        bm25_top_k: int = 30,
        triage_level: str | None = None,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "query": query,
                "expanded_terms": expanded_terms or [],
                "top_k": top_k,
                "mode": mode,
                "vector_top_k": vector_top_k,
                "bm25_top_k": bm25_top_k,
                "triage_level": triage_level,
            }
        )
        return RetrievalResult(
            query=query,
            expanded_query=" ".join([query, *(expanded_terms or [])]),
            mode=mode,
            top_k=top_k,
            vector_top_k=vector_top_k,
            bm25_top_k=bm25_top_k,
            results=self.results[:top_k],
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
        section_heading="Call 999 if:",
        section_type=section_type,
        text=f"{title} {section_type} guidance text.",
        final_score=0.01,
        vector_rank=rank,
        bm25_rank=rank,
        section_bonus=0.004 if section_type == "immediate_action" else 0.0,
    )


def test_graph_runs_emergency_case_end_to_end_with_fake_retriever() -> None:
    retriever = FakeRetriever(
        [
            _hit(1, "immediate_action", "Chest pain"),
            _hit(2, "urgent_advice", "Shortness of breath"),
        ]
    )
    graph = CareGuideGraph(retriever_agent=retriever, retrieval_mode="bm25")

    result = graph.run("Tôi bị đau ngực và khó thở 30 phút")

    assert result["parsed"].symptoms
    assert result["normalized"].normalized_symptoms
    assert result["triage"].triage_level == "emergency"
    assert result["retrieval"].results
    assert result["answer_context"]
    assert result["answer"].triage_level == "emergency"
    assert result["safety"]["passed"] is True
    assert result["final_output"]["triage_level"] == "emergency"
    assert result["final_output"]["related_health_topics"]
    assert retriever.calls[0]["mode"] == "bm25"
    assert retriever.calls[0]["triage_level"] == "emergency"
    assert result["retrieval_query"] == "Tôi bị đau ngực và khó thở 30 phút"
    assert "chest pain" in result["expanded_terms"]


def test_graph_runs_self_care_case_without_required_citation() -> None:
    graph = CareGuideGraph(retriever_agent=FakeRetriever([]), retrieval_mode="bm25")

    result = graph.run("Tôi đau họng nhẹ 1 ngày, không khó thở")

    assert result["triage"].triage_level == "self_care"
    assert result["answer_context"] == []
    assert result["answer"].citations == []
    assert result["safety"]["requires_citation"] is False
    assert result["safety"]["passed"] is True
    assert result["final_output"]["triage_level"] == "self_care"
    assert "shortness of breath" not in result["expanded_terms"]
    assert "difficulty breathing" not in result["expanded_terms"]
    assert "\u006b\u0068\u00f3 \u0074\u0068\u1edf" not in result["retrieval_query"].lower()


def test_graph_positive_retrieval_query_removes_negated_symptoms() -> None:
    retriever = FakeRetriever([_hit(1, "symptoms", "Flu")])
    graph = CareGuideGraph(retriever_agent=retriever, retrieval_mode="bm25")

    result = graph.run(
        "\u0054\u00f4\u0069 \u0073\u1ed1\u0074 39 \u0111\u1ed9, "
        "\u0068\u006f \u0076\u00e0 \u0111\u0061\u0075 \u0068\u1ecd\u006e\u0067 "
        "3 \u006e\u0067\u00e0\u0079, \u006b\u0068\u00f4\u006e\u0067 "
        "\u006b\u0068\u00f3 \u0074\u0068\u1edf"
    )

    assert "\u006b\u0068\u00f4\u006e\u0067 \u006b\u0068\u00f3 \u0074\u0068\u1edf" not in result[
        "retrieval_query"
    ].lower()
    assert "shortness of breath" not in result["expanded_terms"]
    assert retriever.calls[0]["query"] == result["retrieval_query"]


def test_graph_positive_query_handles_multi_term_negation_for_common_cold() -> None:
    retriever = FakeRetriever([_hit(1, "symptoms", "Common cold")])
    graph = CareGuideGraph(retriever_agent=retriever, retrieval_mode="bm25")

    result = graph.run(
        "\u0054\u00f4\u0069 \u0073\u1ed5 \u006d\u0169\u0069, "
        "\u0068\u1eaf\u0074 \u0068\u01a1\u0069 \u006e\u0068\u1eb9 "
        "1 \u006e\u0067\u00e0\u0079, \u006b\u0068\u00f4\u006e\u0067 "
        "\u0073\u1ed1\u0074 \u0063\u0061\u006f \u0068\u0061\u0079 "
        "\u006b\u0068\u00f3 \u0074\u0068\u1edf"
    )

    query = result["retrieval_query"].lower()
    assert "\u0073\u1ed5 \u006d\u0169\u0069" in query
    assert "\u0073\u1ed1\u0074 \u0063\u0061\u006f" not in query
    assert "\u006b\u0068\u00f3 \u0074\u0068\u1edf" not in query
    assert "common cold" in result["expanded_terms"]
    assert "cold symptoms" in result["expanded_terms"]


def test_select_answer_context_filters_low_value_chunks_when_enough_content_exists() -> None:
    hits = [
        _hit(1, "urgent_advice", "Abdominal Pain"),
        _hit(2, "metadata", "Abdominal Pain"),
        _hit(3, "immediate_action", "Stomach ache"),
        _hit(4, "aliases", "Abdominal Pain"),
        _hit(5, "symptoms", "Abdominal Pain"),
    ]

    selected = select_answer_context(hits, top_k=5, min_answerable=3)

    assert [hit.section_type for hit in selected] == [
        "urgent_advice",
        "immediate_action",
        "symptoms",
    ]


def test_select_answer_context_keeps_low_value_chunks_when_content_is_limited() -> None:
    hits = [
        _hit(1, "urgent_advice", "Heat Illness"),
        _hit(2, "metadata", "Heat Illness"),
        _hit(3, "aliases", "Heat Illness"),
    ]

    selected = select_answer_context(hits, top_k=5, min_answerable=3)

    assert [hit.section_type for hit in selected] == ["urgent_advice", "metadata", "aliases"]
