import json
from pathlib import Path

import pytest

from careguide.rag.collect_cdc_sources import (
    cdc_page_to_document,
    cdc_media_to_document,
    classify_cdc_section,
    extract_content_html,
    extract_media_records,
    html_to_text,
    load_cdc_pages,
    load_cdc_queries,
)
from careguide.schemas.document import OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[1]
QUERIES_PATH = ROOT / "data" / "raw" / "official_sources" / "cdc_queries.yaml"
OUTPUT_PATH = ROOT / "data" / "processed" / "cdc_documents.jsonl"


def test_cdc_queries_load() -> None:
    queries = load_cdc_queries(QUERIES_PATH)

    assert len(queries) >= 10
    assert {query.query for query in queries} >= {"flu", "covid", "stroke", "heart attack"}
    assert all(query.max_results >= 1 for query in queries)


def test_cdc_pages_load() -> None:
    pages = load_cdc_pages(QUERIES_PATH)

    assert len(pages) >= 5
    assert {page.id for page in pages} >= {
        "cdc_flu_signs_symptoms",
        "cdc_covid_symptoms",
        "cdc_stroke_signs_symptoms",
    }
    assert all(str(page.url).startswith("https://www.cdc.gov/") for page in pages)


def test_extract_media_records_from_results_payload() -> None:
    payload = {
        "results": [
            {
                "mediaId": 123,
                "name": "Flu symptoms",
                "sourceUrl": "https://www.cdc.gov/flu/signs-symptoms/index.html",
                "description": "CDC flu symptom information",
            }
        ]
    }

    records = extract_media_records(payload)

    assert len(records) == 1
    assert records[0].media_id == "123"
    assert records[0].title == "Flu symptoms"
    assert str(records[0].url).startswith("https://www.cdc.gov/flu")


def test_extract_content_html_from_nested_payload() -> None:
    payload = {"results": [{"content": "<p>Call 911 for emergency warning signs.</p>"}]}

    assert extract_content_html(payload) == "<p>Call 911 for emergency warning signs.</p>"


def test_html_to_text_extracts_paragraphs_and_lists() -> None:
    html = (
        "<h2>Symptoms</h2>"
        "<p>Fever and cough can happen.</p>"
        "<ul><li>Shortness of breath</li><li>Chest pain</li></ul>"
    )

    text = html_to_text(html)

    assert "Symptoms" in text
    assert "Fever and cough can happen." in text
    assert "- Shortness of breath" in text


def test_cdc_media_to_document_schema() -> None:
    queries = load_cdc_queries(QUERIES_PATH)
    record = extract_media_records(
        {
            "results": [
                {
                    "mediaId": "abc",
                    "name": "Stroke warning signs",
                    "sourceUrl": "https://www.cdc.gov/stroke/signs_symptoms.htm",
                    "description": "Stroke warning signs need urgent care.",
                }
            ]
        }
    )[0]

    document = cdc_media_to_document(queries[0], record)

    assert document.source == "CDC"
    assert document.sections


def test_cdc_page_to_document_schema() -> None:
    pages = load_cdc_pages(QUERIES_PATH)
    html = (
        "<main>"
        "<h1>Signs and Symptoms of Flu</h1>"
        "<h2>Symptoms</h2>"
        "<p>People with flu can have fever, cough, and sore throat.</p>"
        "<h2>Emergency warning signs</h2>"
        "<p>Call 911 for trouble breathing or chest pain.</p>"
        "</main>"
    )

    document = cdc_page_to_document(pages[0], html)

    assert document.source == "CDC"
    assert document.sections
    assert any(section.section_type == "urgent_advice" for section in document.sections)


def test_classify_cdc_section() -> None:
    assert classify_cdc_section("Stroke warning signs", "Call 911") == "urgent_advice"
    assert classify_cdc_section("Flu prevention", "Vaccination can help prevent flu") == "prevention"


def test_cdc_documents_output_schema_if_file_exists() -> None:
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        pytest.skip("Run python -m careguide.rag.collect_cdc_sources to create CDC documents")

    documents: list[OfficialHealthDocument] = []
    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            documents.append(OfficialHealthDocument.model_validate(json.loads(line)))

    assert documents
    assert {document.source for document in documents} == {"CDC"}
    assert all(document.sections for document in documents)
