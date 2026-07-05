from pathlib import Path

import pytest

from careguide.agents.retriever import (
    BM25_WEIGHT,
    RRF_K,
    VECTOR_WEIGHT,
    HybridRetrieverAgent,
    RankedItem,
    SimpleBM25,
    build_expanded_query,
    reciprocal_rank,
    section_bonus,
    tokenize,
    weighted_rrf_fusion,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "retriever"
METADATA_PATH = FIXTURES_DIR / "metadata.jsonl"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def _metadata() -> list[dict[str, object]]:
    return [
        {
            "chunk_id": "chunk_chest_0",
            "document_id": "nhs_chest_pain",
            "source": "NHS",
            "url": "https://example.com/chest",
            "title": "Chest pain",
            "topic": "chest pain",
            "priority": "high",
            "symptom_group": "cardiovascular",
            "section_heading": "Call emergency services",
            "section_type": "immediate_action",
            "text": "Chest pain with shortness of breath can be a heart attack emergency.",
        },
        {
            "chunk_id": "chunk_flu_0",
            "document_id": "cdc_flu",
            "source": "CDC",
            "url": "https://example.com/flu",
            "title": "Flu",
            "topic": "flu",
            "priority": "medium",
            "symptom_group": "infectious_disease",
            "section_heading": "Symptoms",
            "section_type": "symptoms",
            "text": "Flu symptoms include fever cough sore throat and body aches.",
        },
    ]


def test_tokenize_uses_lowercase_word_tokens() -> None:
    assert tokenize("Chest pain, COVID-19 & khó thở") == ["chest", "pain", "covid", "19"]


def test_simple_bm25_ranks_keyword_match() -> None:
    documents = [
        tokenize("chest pain shortness breath heart attack"),
        tokenize("fever cough sore throat flu"),
        tokenize("abdominal pain vomiting diarrhea"),
    ]
    bm25 = SimpleBM25(documents)

    results = bm25.search("chest pain", top_k=2)

    assert results[0].index == 0
    assert results[0].rank == 1
    assert results[0].score > 0


def test_reciprocal_rank_starts_from_one() -> None:
    assert reciprocal_rank(1, RRF_K) == pytest.approx(1 / 61)
    with pytest.raises(ValueError):
        reciprocal_rank(0, RRF_K)


def test_weighted_rrf_fusion_merges_rankers_without_raw_score_normalization() -> None:
    hits = weighted_rrf_fusion(
        metadata=_metadata(),
        vector_items=[RankedItem(index=0, rank=1, score=0.42)],
        bm25_items=[RankedItem(index=1, rank=1, score=18.0), RankedItem(index=0, rank=2, score=2.0)],
        top_k=2,
    )

    expected_first_score = (
        VECTOR_WEIGHT * reciprocal_rank(1)
        + BM25_WEIGHT * reciprocal_rank(2)
        + section_bonus("immediate_action")
    )

    assert hits[0].chunk_id == "chunk_chest_0"
    assert hits[0].vector_rank == 1
    assert hits[0].bm25_rank == 2
    assert hits[0].final_score == pytest.approx(expected_first_score)
    assert hits[0].section_bonus == 0.004


def test_build_expanded_query_appends_terms() -> None:
    assert build_expanded_query("đau ngực", ["chest pain", "shortness of breath"]) == (
        "đau ngực chest pain shortness of breath"
    )


def test_hybrid_retriever_bm25_mode_runs_without_faiss_or_model() -> None:
    retriever = HybridRetrieverAgent(
        metadata_path=METADATA_PATH,
        manifest_path=MANIFEST_PATH,
        faiss_path=FIXTURES_DIR / "missing.index",
    )

    result = retriever.run(
        query="Tôi bị sốt và ho",
        expanded_terms=["fever", "cough"],
        mode="bm25",
        top_k=2,
    )

    assert result.mode == "bm25"
    assert result.expanded_query == "Tôi bị sốt và ho fever cough"
    assert result.results[0].title == "Flu"
    assert result.results[0].bm25_rank == 1
