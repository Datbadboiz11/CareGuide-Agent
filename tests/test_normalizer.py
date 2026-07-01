from pathlib import Path

import pytest

from careguide.agents.normalizer import (
    MedicalTermNormalizerAgent,
    load_symptom_vocabulary,
    normalize_clinical_info,
    normalize_terms,
)
from careguide.agents.symptom_parser import parse_symptoms
from careguide.schemas.test_case import TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"
VOCAB_PATH = ROOT / "data" / "processed" / "symptom_vocabulary.json"


def _cases() -> list[TriageTestCase]:
    return load_jsonl_as(TRIAGE_CASES, TriageTestCase)


def test_vocabulary_loads() -> None:
    vocabulary = load_symptom_vocabulary(VOCAB_PATH)

    assert len(vocabulary) >= 80
    assert any(entry.canonical == "fever" for entry in vocabulary)
    assert any(entry.canonical == "shortness of breath" for entry in vocabulary)
    assert any(entry.red_flag_hint for entry in vocabulary)


def test_normalizer_maps_basic_terms() -> None:
    result = normalize_terms(["sốt", "ho", "đau họng"], ["khó thở"])
    by_original = {item.original: item for item in result.normalized_symptoms}

    assert by_original["sốt"].canonical == "fever"
    assert by_original["ho"].canonical == "cough"
    assert by_original["đau họng"].canonical == "sore throat"
    assert by_original["khó thở"].canonical == "shortness of breath"
    assert by_original["khó thở"].negated is True


def test_normalizer_agent_runs_from_parser_output() -> None:
    parser_output = parse_symptoms("Tôi bị sốt 38.8 độ, ho, đau họng 2 ngày nay, không khó thở.")
    result = MedicalTermNormalizerAgent().run(parser_output)
    canonical = {item.canonical for item in result.normalized_symptoms}

    assert {"fever", "cough", "sore throat", "shortness of breath"} <= canonical


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("đau ngực dữ dội", "chest pain"),
        ("khó thở nhiều", "shortness of breath"),
        ("nôn ra máu đỏ tươi", "hematemesis"),
        ("yếu nửa người", "unilateral weakness"),
        ("sưng môi", "lip swelling"),
        ("tiểu ra máu", "hematuria"),
    ],
)
def test_normalizer_handles_red_flag_terms(term: str, expected: str) -> None:
    result = normalize_terms([term])

    assert result.normalized_symptoms[0].canonical == expected
    assert result.normalized_symptoms[0].red_flag_hint is True


def test_normalizer_coverage_on_parser_benchmark() -> None:
    cases = _cases()
    total = 0
    matched = 0

    for case in cases:
        parsed = parse_symptoms(case.user_input)
        result = normalize_clinical_info(parsed)
        total += len(parsed.symptoms) + len(parsed.negated_symptoms)
        matched += len(result.normalized_symptoms)

    assert total > 0
    assert matched / total >= 0.85
