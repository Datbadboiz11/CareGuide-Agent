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
    build_expanded_terms,
    fusion_weights,
    has_emergency_terms,
    low_value_section_penalty,
    reciprocal_rank,
    section_bonus,
    title_topic_bonus,
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
        {
            "chunk_id": "chunk_alias_0",
            "document_id": "medlineplus_dry_mouth",
            "source": "MedlinePlus",
            "url": "https://example.com/dry-mouth",
            "title": "Dry Mouth",
            "topic": "dry mouth",
            "priority": "medium",
            "symptom_group": "general",
            "section_heading": "Also called",
            "section_type": "aliases",
            "text": "Also called xerostomia.",
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
    assert hits[0].low_value_section_penalty == 0.0


def test_build_expanded_query_appends_terms() -> None:
    assert build_expanded_query("đau ngực", ["chest pain", "shortness of breath"]) == (
        "đau ngực chest pain shortness of breath"
    )


def test_dynamic_fusion_weights_prefer_bm25_when_expanded_terms_exist() -> None:
    assert fusion_weights([]) == (0.65, 0.35)
    assert fusion_weights(["stroke"]) == (0.60, 0.40)
    assert fusion_weights(["stroke", "face drooping"]) == (0.45, 0.55)


def test_low_value_sections_are_penalized() -> None:
    assert low_value_section_penalty("metadata") == 0.004
    assert low_value_section_penalty("aliases") == 0.004
    assert low_value_section_penalty("symptoms") == 0.0


def test_title_topic_bonus_uses_expanded_terms() -> None:
    metadata = {"title": "Chest pain", "topic": "chest pain"}

    assert title_topic_bonus(metadata, ["chest pain", "heart attack"]) == 0.004
    assert title_topic_bonus(metadata, ["stroke"]) == 0.0


def test_section_bonus_can_disable_urgent_boost() -> None:
    assert section_bonus("immediate_action", apply_urgent_bonus=False) == 0.0
    assert section_bonus("symptoms", apply_urgent_bonus=False) == 0.002


def test_build_expanded_terms_adds_medical_mapping() -> None:
    terms = build_expanded_terms("Méo miệng, yếu một bên tay chân, nói khó")

    assert "stroke" in terms
    assert "face drooping" in terms
    assert "speech difficulty" in terms


def test_build_expanded_terms_adds_high_risk_mapping() -> None:
    anaphylaxis_terms = build_expanded_terms("Sưng môi, nổi mề đay và khó thở sau khi ăn hải sản")
    sepsis_terms = build_expanded_terms("Sốt rét run, lơ mơ sau nhiễm trùng")
    pregnancy_terms = build_expanded_terms("Đang mang thai bị ra máu âm đạo")

    assert "anaphylaxis" in anaphylaxis_terms
    assert "swollen lips" in anaphylaxis_terms
    assert "sepsis" in sepsis_terms
    assert "confusion" in sepsis_terms
    assert "vaginal bleeding" in pregnancy_terms
    assert "ectopic pregnancy" in pregnancy_terms


def test_has_emergency_terms_from_query_or_expansion() -> None:
    assert has_emergency_terms("Tôi bị đau ngực", []) is True
    assert has_emergency_terms("Tôi bị mệt", ["stroke"]) is True
    assert has_emergency_terms("Tôi bị ho nhẹ", ["cough"]) is False


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
    assert result.expanded_query == "Tôi bị sốt và ho fever cough high temperature"
    assert result.results[0].title == "Flu"
    assert result.results[0].bm25_rank == 1
