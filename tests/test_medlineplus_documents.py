import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from careguide.rag.collect_medlineplus_sources import (
    classify_medlineplus_section,
    html_fragment_to_text,
    medlineplus_topic_to_document,
    parse_medlineplus_xml,
)
from careguide.schemas.document import OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "medlineplus" / "mplus_topics_2026-06-27.xml"
OUTPUT_PATH = ROOT / "data" / "processed" / "medlineplus_documents.jsonl"


def test_html_fragment_to_text_extracts_paragraphs_and_lists() -> None:
    fragment = (
        "<p>Get medical help immediately if symptoms are severe.</p>"
        "<ul><li>Chest pain</li><li>Trouble breathing</li></ul>"
    )

    text = html_fragment_to_text(fragment)

    assert "Get medical help immediately" in text
    assert "- Chest pain" in text
    assert "- Trouble breathing" in text


def test_medlineplus_topic_to_document_schema() -> None:
    xml = (
        '<health-topic title="Abdominal Pain" url="https://medlineplus.gov/abdominalpain.html" '
        'id="3061" language="English" date-created="01/07/2003">'
        "<also-called>Bellyache</also-called>"
        "<full-summary>&lt;p&gt;Get medical help immediately for severe abdominal pain.&lt;/p&gt;</full-summary>"
        '<group url="https://medlineplus.gov/digestivesystem.html" id="2">Digestive System</group>'
        '<group url="https://medlineplus.gov/symptoms.html" id="31">Symptoms</group>'
        '<site title="Abdominal Pain" url="https://medlineplus.gov/ency/article/003120.htm">'
        "<information-category>Patient Handouts</information-category>"
        "<organization>Medical Encyclopedia</organization>"
        "</site>"
        "</health-topic>"
    )

    document = medlineplus_topic_to_document(ET.fromstring(xml))

    assert document.source == "MedlinePlus"
    assert document.title == "Abdominal Pain"
    assert document.symptom_group == "gastrointestinal"
    assert document.sections
    assert any(section.section_type == "urgent_advice" for section in document.sections)


def test_parse_medlineplus_xml_reads_sample_from_raw_file() -> None:
    if not RAW_PATH.exists():
        pytest.skip("Download MedlinePlus XML to data/raw/medlineplus first")

    documents = parse_medlineplus_xml(RAW_PATH, max_documents=5)

    assert len(documents) == 5
    assert {document.source for document in documents} == {"MedlinePlus"}
    assert all(document.title for document in documents)
    assert all(document.sections for document in documents)


def test_classify_medlineplus_section() -> None:
    assert classify_medlineplus_section("Summary", "Call 911 for emergency symptoms") == "urgent_advice"
    assert classify_medlineplus_section("Summary", "Symptoms include fever and cough") == "symptoms"
    assert classify_medlineplus_section("Summary", "Treatment may include medicine") == "treatment"


def test_medlineplus_documents_output_schema_if_file_exists() -> None:
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        pytest.skip("Run python -m careguide.rag.collect_medlineplus_sources to create MedlinePlus documents")

    documents: list[OfficialHealthDocument] = []
    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            documents.append(OfficialHealthDocument.model_validate(json.loads(line)))

    assert documents
    assert {document.source for document in documents} == {"MedlinePlus"}
    assert all(document.sections for document in documents)
