import json
from pathlib import Path

import pytest

from careguide.rag.chunk_official_rag_corpus import (
    build_chunk_id,
    chunk_document,
    count_words,
    split_text_by_words,
)
from careguide.schemas.document import DocumentSection, OfficialHealthDocument
from careguide.schemas.rag import RagChunk


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "processed" / "official_rag_chunks.jsonl"


def _document() -> OfficialHealthDocument:
    return OfficialHealthDocument(
        id="nhs_chest_pain",
        source="NHS",
        url="https://www.nhs.uk/symptoms/chest-pain/",
        title="Chest pain",
        topic="chest pain",
        priority="high",
        symptom_group="cardiovascular",
        sections=[
            DocumentSection(
                heading="Immediate action",
                content="Call emergency services for severe chest pain with trouble breathing.",
                section_type="immediate_action",
            )
        ],
    )


def test_build_chunk_id_is_stable() -> None:
    assert build_chunk_id("nhs_chest_pain", 2, 3) == "nhs_chest_pain__section_2__chunk_3"


def test_split_text_by_words_uses_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(12))

    chunks = split_text_by_words(text, max_words=5, overlap_words=2)

    assert chunks == [
        "word0 word1 word2 word3 word4",
        "word3 word4 word5 word6 word7",
        "word6 word7 word8 word9 word10",
        "word9 word10 word11",
    ]


def test_chunk_document_preserves_metadata() -> None:
    chunks = chunk_document(_document(), max_words=50, overlap_words=10)

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "nhs_chest_pain__section_0__chunk_0"
    assert chunks[0].source == "NHS"
    assert chunks[0].section_type == "immediate_action"
    assert "Call emergency services" in chunks[0].text


def test_count_words() -> None:
    assert count_words("one two three") == 3


def test_official_rag_chunks_output_schema_if_file_exists() -> None:
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        pytest.skip("Run python -m careguide.rag.chunk_official_rag_corpus to create official RAG chunks")

    chunks: list[RagChunk] = []
    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            chunks.append(RagChunk.model_validate(json.loads(line)))

    assert chunks
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert {chunk.source for chunk in chunks} >= {"NHS", "CDC", "MedlinePlus"}
    assert all(chunk.word_count > 0 for chunk in chunks)
    assert all(chunk.word_count <= 450 for chunk in chunks)
