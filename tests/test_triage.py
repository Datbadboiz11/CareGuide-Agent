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


def test_triage_classifies_carbon_monoxide_pattern_as_emergency() -> None:
    result = _classify(
        "\u0054\u00f4\u0069 \u0111\u0061\u0075 \u0111\u1ea7\u0075 "
        "\u0063\u0068\u00f3\u006e\u0067 \u006d\u1eb7\u0074 "
        "\u0073\u0061\u0075 \u006b\u0068\u0069 \u1edf "
        "\u0074\u0072\u006f\u006e\u0067 \u0070\u0068\u00f2\u006e\u0067 "
        "\u006b\u00ed\u006e \u0063\u00f3 \u0062\u1ebf\u0070 \u0067\u0061\u0073"
    )

    assert result.triage_level == "emergency"
    assert result.requires_emergency is True


def test_triage_classifies_dengue_warning_pattern_as_urgent() -> None:
    result = _classify(
        "\u0053\u1ed1\u0074 \u0063\u0061\u006f \u0073\u0061\u0075 "
        "\u006b\u0068\u0069 \u0111\u0069 \u0076\u00f9\u006e\u0067 "
        "\u006e\u0068\u0069\u1ec7\u0074 \u0111\u1edb\u0069, "
        "\u0111\u0061\u0075 \u006e\u0067\u01b0\u1eddi \u0076\u00e0 "
        "\u0063\u0068\u1ea3\u0079 \u006d\u00e1\u0075 \u0063\u0068\u00e2\u006e "
        "\u0072\u0103\u006e\u0067"
    )

    assert result.triage_level == "urgent_visit"
    assert result.requires_urgent is True
    assert result.requires_emergency is False


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
