from pathlib import Path

import pytest

from careguide.agents.normalizer import normalize_clinical_info
from careguide.agents.red_flag import RedFlagAgent, detect_red_flags, load_red_flag_rules
from careguide.agents.symptom_parser import parse_symptoms
from careguide.schemas.test_case import TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"
RULES_PATH = ROOT / "src" / "careguide" / "safety" / "red_flags.yaml"


def _cases() -> list[TriageTestCase]:
    return load_jsonl_as(TRIAGE_CASES, TriageTestCase)


def _detect(text: str):
    parsed = parse_symptoms(text)
    normalized = normalize_clinical_info(parsed)
    return detect_red_flags(parsed, normalized)


def test_red_flag_rules_load() -> None:
    rules = load_red_flag_rules(RULES_PATH)

    assert "canonical_rules" in rules
    assert "vital_rules" in rules
    assert "chest pain" in rules["canonical_rules"]
    assert "shortness of breath" in rules["canonical_rules"]


def test_red_flag_agent_detects_emergency_chest_pain() -> None:
    result = _detect("Tôi đau ngực dữ dội, khó thở và vã mồ hôi lạnh.")

    assert result.requires_emergency is True
    assert result.highest_severity == "emergency"
    assert any(flag.severity == "emergency" for flag in result.red_flags)


def test_red_flag_agent_respects_negation() -> None:
    result = _detect("Tôi sốt 37.8 độ, hơi mệt, không khó thở, không đau ngực.")

    assert result.requires_emergency is False
    assert all(flag.canonical not in {"shortness of breath", "chest pain"} for flag in result.red_flags)


def test_red_flag_agent_detects_carbon_monoxide_exposure_pattern() -> None:
    result = _detect(
        "\u0054\u00f4\u0069 \u0111\u0061\u0075 \u0111\u1ea7\u0075 "
        "\u0063\u0068\u00f3\u006e\u0067 \u006d\u1eb7\u0074 "
        "\u0073\u0061\u0075 \u006b\u0068\u0069 \u1edf "
        "\u0074\u0072\u006f\u006e\u0067 \u0070\u0068\u00f2\u006e\u0067 "
        "\u006b\u00ed\u006e \u0063\u00f3 \u0062\u1ebf\u0070 \u0067\u0061\u0073"
    )

    assert result.requires_emergency is True
    assert any(flag.canonical == "carbon monoxide poisoning" for flag in result.red_flags)


def test_red_flag_agent_detects_dengue_warning_pattern() -> None:
    result = _detect(
        "\u0053\u1ed1\u0074 \u0063\u0061\u006f \u0073\u0061\u0075 "
        "\u006b\u0068\u0069 \u0111\u0069 \u0076\u00f9\u006e\u0067 "
        "\u006e\u0068\u0069\u1ec7\u0074 \u0111\u1edb\u0069, "
        "\u0111\u0061\u0075 \u006e\u0067\u01b0\u1eddi \u0076\u00e0 "
        "\u0063\u0068\u1ea3\u0079 \u006d\u00e1\u0075 \u0063\u0068\u00e2\u006e "
        "\u0072\u0103\u006e\u0067"
    )

    assert result.requires_urgent is True
    assert result.requires_emergency is False
    assert any(flag.canonical == "dengue" for flag in result.red_flags)


@pytest.mark.parametrize(
    ("text", "expected_severity"),
    [
        ("Tôi khó thở nhiều, môi tím, SpO2 88%.", "emergency"),
        ("Tôi bị hen, hơi khó thở khi đi lại, SpO2 94%.", "urgent"),
        ("Tôi sốt 40 độ và phát ban tím.", "emergency"),
        ("Tôi đau đầu, huyết áp 170/100.", "urgent"),
    ],
)
def test_red_flag_agent_uses_vitals(text: str, expected_severity: str) -> None:
    result = _detect(text)

    assert result.highest_severity == expected_severity


def test_red_flag_agent_class_runs() -> None:
    parsed = parse_symptoms("Tôi nôn ra máu đỏ tươi và choáng váng.")
    normalized = normalize_clinical_info(parsed)
    result = RedFlagAgent().run(parsed, normalized)

    assert result.requires_emergency is True


def test_all_emergency_benchmark_cases_require_emergency() -> None:
    emergency_cases = [case for case in _cases() if case.expected_triage == "emergency"]

    missed: list[str] = []
    for case in emergency_cases:
        parsed = parse_symptoms(case.user_input)
        normalized = normalize_clinical_info(parsed)
        result = detect_red_flags(parsed, normalized)
        if not result.requires_emergency:
            missed.append(case.id)

    assert missed == []


def test_self_care_benchmark_cases_do_not_require_emergency() -> None:
    self_care_cases = [case for case in _cases() if case.expected_triage == "self_care"]

    false_emergency: list[str] = []
    for case in self_care_cases:
        parsed = parse_symptoms(case.user_input)
        normalized = normalize_clinical_info(parsed)
        result = detect_red_flags(parsed, normalized)
        if result.requires_emergency:
            false_emergency.append(case.id)

    assert false_emergency == []
