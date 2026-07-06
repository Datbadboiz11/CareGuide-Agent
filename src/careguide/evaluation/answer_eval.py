from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from careguide.agents.answer import generate_answer
from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.retrieval import RetrievalResult
from careguide.schemas.triage import TriageLevel, TriageResult


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = ROOT / "data" / "test_cases" / "answer_eval_cases.jsonl"


class AnswerEvalCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    parsed: ParsedClinicalInfo
    triage: TriageResult
    red_flags: RedFlagResult
    retrieval: RetrievalResult
    expected_triage_level: TriageLevel
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    requires_citation: bool = True
    requires_disclaimer: bool = True


def main() -> None:
    _configure_stdout()
    args = _parse_args()
    cases = load_cases(args.cases)
    metrics = evaluate_answer_cases(cases)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def evaluate_answer_cases(cases: list[AnswerEvalCase]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for case in cases:
        answer = generate_answer(case.parsed, case.triage, case.red_flags, case.retrieval)
        details.append(evaluate_answer(case, answer.model_dump(mode="json")))
    return aggregate_answer_metrics(details)


def evaluate_answer(case: AnswerEvalCase, answer: dict[str, Any]) -> dict[str, Any]:
    answer_text = json.dumps(answer, ensure_ascii=False).lower()
    must_include_pass = all(term.lower() in answer_text for term in case.must_include)
    must_not_include_pass = all(term.lower() not in answer_text for term in case.must_not_include)
    citation_present = bool(answer.get("citations"))
    citation_requirement_pass = citation_present if case.requires_citation else True
    disclaimer_present = bool(answer.get("safety_disclaimer"))
    disclaimer_requirement_pass = disclaimer_present if case.requires_disclaimer else True
    triage_correct = answer.get("triage_level") == case.expected_triage_level

    return {
        "id": case.id,
        "triage_correct": triage_correct,
        "citation_present": citation_present,
        "citation_requirement_pass": citation_requirement_pass,
        "disclaimer_present": disclaimer_present,
        "disclaimer_requirement_pass": disclaimer_requirement_pass,
        "must_include_pass": must_include_pass,
        "must_not_include_pass": must_not_include_pass,
        "safe_escalation_pass": safe_escalation_pass(case.expected_triage_level, answer_text),
        "triage_level": answer.get("triage_level"),
        "citation_count": len(answer.get("citations", [])),
    }


def aggregate_answer_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(details)
    if total == 0:
        return {"total": 0, "details": []}

    return {
        "total": total,
        "triage_accuracy": _mean([detail["triage_correct"] for detail in details]),
        "citation_present_rate": _mean([detail["citation_present"] for detail in details]),
        "citation_requirement_pass_rate": _mean([detail["citation_requirement_pass"] for detail in details]),
        "disclaimer_present_rate": _mean([detail["disclaimer_present"] for detail in details]),
        "disclaimer_requirement_pass_rate": _mean([detail["disclaimer_requirement_pass"] for detail in details]),
        "must_include_pass_rate": _mean([detail["must_include_pass"] for detail in details]),
        "must_not_include_pass_rate": _mean([detail["must_not_include_pass"] for detail in details]),
        "safe_escalation_pass_rate": _mean([detail["safe_escalation_pass"] for detail in details]),
        "details": details,
    }


def safe_escalation_pass(level: str, answer_text: str) -> bool:
    if level == "emergency":
        return "cấp cứu" in answer_text or "khẩn cấp" in answer_text
    if level == "urgent_visit":
        return "khám sớm" in answer_text or "đánh giá sớm" in answer_text
    return True


def load_cases(path: str | Path) -> list[AnswerEvalCase]:
    cases: list[AnswerEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                cases.append(AnswerEvalCase.model_validate(json.loads(line)))
    return cases


def _mean(values: list[float | bool]) -> float:
    return sum(float(value) for value in values) / len(values) if values else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    return parser.parse_args()


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
