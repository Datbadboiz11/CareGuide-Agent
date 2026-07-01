from collections import Counter
from pathlib import Path

from careguide.schemas.test_case import SafetyTestCase, TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"
SAFETY_CASES = ROOT / "data" / "test_cases" / "safety_cases.jsonl"


def test_triage_cases_are_valid_and_balanced() -> None:
    cases = load_jsonl_as(TRIAGE_CASES, TriageTestCase)

    assert len(cases) == 100
    assert len({case.id for case in cases}) == len(cases)
    assert Counter(case.expected_triage for case in cases) == {
        "self_care": 25,
        "routine_visit": 25,
        "urgent_visit": 25,
        "emergency": 25,
    }


def test_triage_cases_have_expected_benchmark_coverage() -> None:
    cases = load_jsonl_as(TRIAGE_CASES, TriageTestCase)

    assert any(case.expected_negated_symptoms for case in cases)
    assert any(case.expected_vitals for case in cases)
    assert any(case.expected_red_flags for case in cases)
    assert any(case.expected_missing_info for case in cases)
    assert any(case.risk_factors for case in cases)
    assert {case.difficulty for case in cases} == {"simple", "medium", "complex"}


def test_safety_cases_are_valid() -> None:
    cases = load_jsonl_as(SAFETY_CASES, SafetyTestCase)

    assert len(cases) == 40
    assert len({case.id for case in cases}) == len(cases)
    assert Counter(case.expected_safety_pass for case in cases) == {
        True: 12,
        False: 28,
    }


def test_safety_cases_cover_core_violation_types() -> None:
    cases = load_jsonl_as(SAFETY_CASES, SafetyTestCase)
    violations = {violation for case in cases for violation in case.expected_violations}

    expected_core_violations = {
        "diagnosis_violation",
        "prescription_violation",
        "dosage_violation",
        "delayed_emergency",
        "missing_disclaimer",
        "missed_red_flag",
        "over_reassurance",
        "triage_mismatch",
    }

    assert expected_core_violations <= violations
