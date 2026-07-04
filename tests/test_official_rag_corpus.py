import json
from pathlib import Path

import pytest

from careguide.rag.build_official_rag_corpus import build_official_corpus, count_by_source, read_documents_jsonl
from careguide.schemas.document import OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "processed" / "official_rag_corpus.jsonl"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "official_rag_corpus"


def test_build_official_corpus_validates_and_deduplicates() -> None:
    first = FIXTURES_DIR / "first.jsonl"
    second = FIXTURES_DIR / "second.jsonl"

    documents = build_official_corpus([first, second])

    assert len(documents) == 2
    assert count_by_source(documents) == {"NHS": 1, "CDC": 1}


def test_read_documents_jsonl_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        read_documents_jsonl(FIXTURES_DIR / "invalid.jsonl")


def test_official_rag_corpus_output_schema_if_file_exists() -> None:
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        pytest.skip("Run python -m careguide.rag.build_official_rag_corpus to create official RAG corpus")

    documents: list[OfficialHealthDocument] = []
    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            documents.append(OfficialHealthDocument.model_validate(json.loads(line)))

    counts = count_by_source(documents)

    assert counts["NHS"] >= 700
    assert counts["CDC"] >= 20
    assert counts["MedlinePlus"] >= 1000
    assert all(document.sections for document in documents)
