from pathlib import Path

from careguide.agents.normalizer import normalize_clinical_info
from careguide.agents.questioning import QuestioningAgent, generate_followup_questions
from careguide.agents.red_flag import detect_red_flags
from careguide.agents.symptom_parser import parse_symptoms
from careguide.agents.triage import classify_triage
from careguide.schemas.test_case import TriageTestCase
from careguide.utils.jsonl import load_jsonl_as


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_CASES = ROOT / "data" / "test_cases" / "vietnamese_triage_cases.jsonl"


def _cases() -> list[TriageTestCase]:
    return load_jsonl_as(TRIAGE_CASES, TriageTestCase)


def _question(text: str):
    parsed = parse_symptoms(text)
    normalized = normalize_clinical_info(parsed)
    red_flags = detect_red_flags(parsed, normalized)
    triage = classify_triage(parsed, normalized, red_flags)
    result = generate_followup_questions(parsed, normalized, red_flags, triage)
    return result, triage


def test_questioning_skips_emergency() -> None:
    result, triage = _question("Tôi đau ngực dữ dội, khó thở và vã mồ hôi lạnh.")

    assert triage.triage_level == "emergency"
    assert result.should_ask is False
    assert result.questions == []
    assert result.skipped_reason


def test_questioning_asks_abdominal_red_flags() -> None:
    result, triage = _question("Tôi bị đau bụng từ hôm qua.")
    questions = [item.question for item in result.questions]

    assert triage.triage_level in {"self_care", "routine_visit", "urgent_visit"}
    assert result.should_ask is True
    assert any("vị trí" in question and "nôn ra máu" in question for question in questions)


def test_questioning_asks_respiratory_red_flags() -> None:
    result, _ = _question("Tôi ho và đau họng 2 ngày, không khó thở.")
    questions = [item.question for item in result.questions]

    assert result.should_ask is True
    assert any("khó thở" in question and "đau ngực" in question for question in questions)


def test_questioning_agent_class_runs() -> None:
    parsed = parse_symptoms("Tôi sốt 39 độ đã 3 ngày, rất mệt và uống nước kém.")
    normalized = normalize_clinical_info(parsed)
    red_flags = detect_red_flags(parsed, normalized)
    triage = classify_triage(parsed, normalized, red_flags)
    result = QuestioningAgent().run(parsed, normalized, red_flags, triage)

    assert triage.triage_level == "urgent_visit"
    assert result.should_ask is True
    assert 1 <= len(result.questions) <= 3
    assert all(question.priority in {"high", "medium", "low"} for question in result.questions)


def test_questioning_limits_questions_on_benchmark() -> None:
    for case in _cases():
        parsed = parse_symptoms(case.user_input)
        normalized = normalize_clinical_info(parsed)
        red_flags = detect_red_flags(parsed, normalized)
        triage = classify_triage(parsed, normalized, red_flags)
        result = generate_followup_questions(parsed, normalized, red_flags, triage)

        if triage.triage_level == "emergency":
            assert result.should_ask is False
            assert result.questions == []
        elif triage.triage_level == "urgent_visit":
            assert len(result.questions) <= 3
        else:
            assert len(result.questions) <= 5

