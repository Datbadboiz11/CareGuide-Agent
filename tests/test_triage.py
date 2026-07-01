from collections import Counter
from pathlib import Path

import pytest

from careguide.agents.normalizer import normalize_clinical_info
from careguide.agents.red_flag import detect_red_flags
from careguide.agents.symptom_parser import parse_symptoms
from careguide.agents.triage import TriageAgent, classify_triage
from careguide.schemas.test_case import TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"


def _cases() -> list[TriageTestCase]:
    return load_jsonl_as(TRIAGE_CASES, TriageTestCase)


def _classify(text: str):
    parsed = parse_symptoms(text)
    normalized = normalize_clinical_info(parsed)
    red_flags = detect_red_flags(parsed, normalized)
    return classify_triage(parsed, normalized, red_flags)


def test_triage_classifies_example_self_care() -> None:
    result = _classify("Tôi bị sốt 38.8 độ, ho, đau họng 2 ngày nay, không khó thở.")

    assert result.triage_level in {"self_care", "urgent_visit"}
    assert result.requires_emergency is False


def test_triage_classifies_example_emergency() -> None:
    result = _classify("Tôi đau ngực dữ dội, khó thở và vã mồ hôi lạnh.")

    assert result.triage_level == "emergency"
    assert result.requires_emergency is True
    assert result.red_flags


def test_triage_agent_class_runs() -> None:
    parsed = parse_symptoms("Tôi ho khan gần 3 tuần, không sốt, không khó thở.")
    normalized = normalize_clinical_info(parsed)
    red_flags = detect_red_flags(parsed, normalized)
    result = TriageAgent().run(parsed, normalized, red_flags)

    assert result.triage_level == "routine_visit"


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.id)
def test_triage_matches_benchmark(case: TriageTestCase) -> None:
    result = _classify(case.user_input)

    assert result.triage_level == case.expected_triage


def test_triage_benchmark_distribution() -> None:
    predicted = Counter(_classify(case.user_input).triage_level for case in _cases())

    assert predicted == {
        "self_care": 25,
        "routine_visit": 25,
        "urgent_visit": 25,
        "emergency": 25,
    }
