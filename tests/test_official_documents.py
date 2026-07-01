import json
from pathlib import Path

import pytest

from careguide.rag.collect_nhs_sources import load_sources
from careguide.schemas.document import OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "raw" / "official_sources" / "official_sources.yaml"
OUTPUT_PATH = ROOT / "data" / "processed" / "official_health_documents.jsonl"


def test_official_sources_config_has_initial_nhs_symptom_pages() -> None:
    sources = load_sources(SOURCES_PATH)

    assert len(sources) == 4
    assert {source.id for source in sources} == {
        "nhs_chest_pain",
        "nhs_shortness_of_breath",
        "nhs_headaches",
        "nhs_stomach_ache",
    }
    assert all(source.source == "NHS" for source in sources)
    assert all(str(source.url).startswith("https://www.nhs.uk/symptoms/") for source in sources)
    assert all(source.priority == "high" for source in sources)


def test_official_sources_config_topics_are_unique() -> None:
    sources = load_sources(SOURCES_PATH)
    topics = [source.topic for source in sources]

    assert len(topics) == len(set(topics))


def test_official_documents_output_schema_if_file_exists() -> None:
    if not OUTPUT_PATH.exists():
        pytest.skip("Run python -m careguide.rag.collect_nhs_sources to create official documents")

    documents: list[OfficialHealthDocument] = []
    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            documents.append(OfficialHealthDocument.model_validate(json.loads(line)))

    assert len(documents) == 4
    assert {document.source for document in documents} == {"NHS"}
    assert all(document.sections for document in documents)
    assert any(
        section.section_type in {"immediate_action", "urgent_advice", "non_urgent_advice"}
        for document in documents
        for section in document.sections
    )
