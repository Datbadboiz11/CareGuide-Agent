from pathlib import Path

import pytest

from careguide.agents.symptom_parser import parse_symptoms
from careguide.schemas.test_case import TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"


def _cases() -> list[TriageTestCase]:
    return load_jsonl_as(TRIAGE_CASES, TriageTestCase)


def _matches(expected: str, actual_items: list[str]) -> bool:
    return any(expected in actual or actual in expected for actual in actual_items)


def test_parser_extracts_example_fields() -> None:
    parsed = parse_symptoms("Tôi bị sốt 38.8 độ, ho, đau họng 2 ngày nay, không khó thở.")

    assert "sốt" in parsed.symptoms
    assert "ho" in parsed.symptoms
    assert "đau họng" in parsed.symptoms
    assert "khó thở" in parsed.negated_symptoms
    assert parsed.duration == "2 ngày"
    assert parsed.vitals["temperature"] == 38.8


def test_parser_extracts_minutes_and_hours_duration() -> None:
    chest_pain = parse_symptoms("Tôi bị đau ngực và khó thở 30 phút.")
    fever = parse_symptoms("Tôi bị sốt và đau đầu 2 giờ.")

    assert chest_pain.duration == "30 phút"
    assert fever.duration == "2 giờ"


def test_parser_extracts_head_injury_confusion_and_knee_pain_terms() -> None:
    head_injury = parse_symptoms("Ngã đập đầu, đau đầu tăng dần, nôn và lú lẫn.")
    knee_pain = parse_symptoms("Tôi đau gối âm ỉ 3 tuần, không sốt.")

    assert "ngã đập đầu" in head_injury.symptoms
    assert "lú lẫn" in head_injury.symptoms
    assert "đau gối" in knee_pain.symptoms


def test_parser_runs_on_all_triage_cases() -> None:
    for case in _cases():
        parsed = parse_symptoms(case.user_input)

        assert parsed.raw_text == case.user_input
        assert parsed.symptoms or parsed.negated_symptoms


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.id)
def test_parser_extracts_expected_vitals(case: TriageTestCase) -> None:
    parsed = parse_symptoms(case.user_input)

    for key, expected_value in case.expected_vitals.items():
        assert key in parsed.vitals
        if isinstance(expected_value, float):
            assert parsed.vitals[key] == pytest.approx(expected_value)
        else:
            assert parsed.vitals[key] == expected_value


def test_parser_symptom_coverage_on_benchmark() -> None:
    cases = _cases()
    total = 0
    matched = 0

    for case in cases:
        parsed = parse_symptoms(case.user_input)
        for expected in case.expected_symptoms:
            total += 1
            if _matches(expected, parsed.symptoms):
                matched += 1

    assert matched / total >= 0.8


def test_parser_negation_coverage_on_benchmark() -> None:
    cases = [case for case in _cases() if case.expected_negated_symptoms]
    total = 0
    matched = 0

    for case in cases:
        parsed = parse_symptoms(case.user_input)
        for expected in case.expected_negated_symptoms:
            total += 1
            if _matches(expected, parsed.negated_symptoms):
                matched += 1

    assert matched / total >= 0.75
