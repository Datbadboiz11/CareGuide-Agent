from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from careguide.graph.careguide_graph import CareGuideGraph
from careguide.graph.state import CareGuideState
from careguide.schemas.retrieval import RetrievalHit, RetrievalMode
from careguide.schemas.triage import TriageLevel


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = ROOT / "data" / "test_cases" / "e2e_eval_cases.jsonl"
DEFAULT_REPORT_PATH = ROOT / "reports" / "evaluation" / "e2e_eval_report.json"
DEFAULT_FAILURES_PATH = ROOT / "reports" / "evaluation" / "e2e_failures.jsonl"
LOW_VALUE_SECTION_TYPES = {"metadata", "aliases"}


class E2EEvalCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected_triage_level: TriageLevel
    expected_symptoms_any: list[str] = Field(default_factory=list)
    expected_expanded_terms_any: list[str] = Field(default_factory=list)
    expected_retrieval_titles_any: list[str] = Field(default_factory=list)
    expected_answer_context_titles_any: list[str] = Field(default_factory=list)
    expected_section_types_any: list[str] = Field(default_factory=list)
    min_answerable_chunks: int = Field(default=3, ge=0)
    must_include: list[str] = Field(default_factory=list)
    must_include_any: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    requires_citation: bool = True
    requires_disclaimer: bool = True
    requires_safe_escalation: bool = False


def main() -> None:
    _configure_stdout()
    args = _parse_args()
    cases = load_cases(args.cases)
    graph = CareGuideGraph(
        retrieval_mode=args.mode,
        top_k=args.top_k,
        vector_top_k=args.vector_top_k,
        bm25_top_k=args.bm25_top_k,
    )
    metrics = evaluate_e2e_cases(cases, graph)
    write_report(metrics, args.report_path, args.failures_path)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def evaluate_e2e_cases(cases: list[E2EEvalCase], graph: Any) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for case in cases:
        try:
            state = graph.run(case.input)
            details.append(evaluate_e2e_result(case, state))
        except Exception as exc:
            details.append(runtime_failure_detail(case, exc))
    return aggregate_e2e_metrics(details)


def evaluate_e2e_result(case: E2EEvalCase, state: CareGuideState) -> dict[str, Any]:
    parsed = state["parsed"]
    triage = state["triage"]
    retrieval = state["retrieval"]
    answer_context = state.get("answer_context", [])
    final_output = state["final_output"]
    safety = state.get("safety", {})

    top_titles = [hit.title for hit in retrieval.results]
    top_section_types = [hit.section_type for hit in retrieval.results]
    answer_context_titles = [hit.title for hit in answer_context]
    answer_context_section_types = [hit.section_type for hit in answer_context]
    answerable_context_count = count_answerable(answer_context)
    answer_text = build_answer_text(final_output)

    expected_context_titles = case.expected_answer_context_titles_any or case.expected_retrieval_titles_any
    checks = {
        "runtime_pass": not state.get("errors"),
        "parser_symptom_hit": matches_any(parsed.symptoms, case.expected_symptoms_any),
        "normalizer_expansion_hit": matches_any(state.get("expanded_terms", []), case.expected_expanded_terms_any),
        "triage_correct": triage.triage_level == case.expected_triage_level,
        "retrieval_hit_at_5_title": matches_any(top_titles, case.expected_retrieval_titles_any),
        "retrieval_hit_at_5_section_type": matches_any(top_section_types, case.expected_section_types_any),
        "answer_context_has_expected_title": matches_any(answer_context_titles, expected_context_titles),
        "min_answerable_chunks_pass": answerable_context_count >= case.min_answerable_chunks,
        "citation_requirement_pass": (
            bool(final_output.get("citations")) if case.requires_citation else True
        ),
        "disclaimer_requirement_pass": (
            bool(final_output.get("safety_disclaimer")) if case.requires_disclaimer else True
        ),
        "safe_escalation_pass": safe_escalation_pass(case, answer_text),
        "must_include_pass": all_contains(answer_text, case.must_include),
        "must_include_any_pass": matches_any_text(answer_text, case.must_include_any),
        "must_not_include_pass": not contains_any_text(answer_text, case.must_not_include),
        "safety_pass": bool(safety.get("passed", False)),
    }
    failure_stage, reason = classify_failure(checks)

    return {
        "id": case.id,
        "input": case.input,
        "passed": all(checks.values()),
        "failure_stage": failure_stage,
        "reason": reason,
        "checks": checks,
        "triage_level": triage.triage_level,
        "expected_triage_level": case.expected_triage_level,
        "parsed_symptoms": parsed.symptoms,
        "expanded_terms": state.get("expanded_terms", []),
        "top_titles": top_titles,
        "top_section_types": top_section_types,
        "answer_context_titles": answer_context_titles,
        "answer_context_section_types": answer_context_section_types,
        "answerable_chunks": answerable_context_count,
        "low_value_answer_context_chunks": len(answer_context) - answerable_context_count,
        "citation_count": len(final_output.get("citations", [])),
        "safety": safety,
    }


def aggregate_e2e_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(details)
    if total == 0:
        return {"total": 0, "details": []}

    return {
        "total": total,
        "passed_rate": _mean([detail["passed"] for detail in details]),
        "parser_symptom_hit_rate": _mean_check(details, "parser_symptom_hit"),
        "normalizer_expansion_hit_rate": _mean_check(details, "normalizer_expansion_hit"),
        "e2e_triage_accuracy": _mean_check(details, "triage_correct"),
        "e2e_retrieval_hit_at_5_title": _mean_check(details, "retrieval_hit_at_5_title"),
        "e2e_retrieval_hit_at_5_section_type": _mean_check(details, "retrieval_hit_at_5_section_type"),
        "e2e_answer_context_has_expected_title": _mean_check(details, "answer_context_has_expected_title"),
        "e2e_min_answerable_chunks_pass_rate": _mean_check(details, "min_answerable_chunks_pass"),
        "e2e_citation_requirement_pass_rate": _mean_check(details, "citation_requirement_pass"),
        "e2e_disclaimer_requirement_pass_rate": _mean_check(details, "disclaimer_requirement_pass"),
        "e2e_safe_escalation_pass_rate": _mean_check(details, "safe_escalation_pass"),
        "e2e_must_include_pass_rate": _mean_check(details, "must_include_pass"),
        "e2e_must_include_any_pass_rate": _mean_check(details, "must_include_any_pass"),
        "e2e_must_not_include_pass_rate": _mean_check(details, "must_not_include_pass"),
        "e2e_safety_pass_rate": _mean_check(details, "safety_pass"),
        "failure_stage_counts": failure_stage_counts(details),
        "details": details,
    }


def classify_failure(checks: dict[str, bool]) -> tuple[str | None, str | None]:
    stages = (
        ("runtime_pass", "runtime_error", "Graph raised errors."),
        ("parser_symptom_hit", "parser_error", "Expected symptom was not found in parsed symptoms."),
        ("normalizer_expansion_hit", "normalizer_error", "Expected expanded term was not found."),
        ("triage_correct", "triage_error", "Triage level did not match expected level."),
        ("retrieval_hit_at_5_title", "retrieval_error", "Expected title was not found in retrieval top 5."),
        (
            "retrieval_hit_at_5_section_type",
            "retrieval_error",
            "Expected section type was not found in retrieval top 5.",
        ),
        (
            "answer_context_has_expected_title",
            "answer_context_error",
            "Expected title was not found in answer context.",
        ),
        (
            "min_answerable_chunks_pass",
            "answer_context_error",
            "Answer context did not contain enough answerable chunks.",
        ),
        ("citation_requirement_pass", "answer_error", "Citation requirement was not satisfied."),
        ("disclaimer_requirement_pass", "answer_error", "Disclaimer requirement was not satisfied."),
        ("safe_escalation_pass", "answer_error", "Safe escalation requirement was not satisfied."),
        ("must_include_pass", "answer_error", "Required answer text was missing."),
        ("must_include_any_pass", "answer_error", "None of the optional required answer terms appeared."),
        ("must_not_include_pass", "safety_error", "Forbidden answer text appeared."),
        ("safety_pass", "safety_error", "Safety check did not pass."),
    )
    for check_name, stage, reason in stages:
        if not checks.get(check_name, False):
            return stage, reason
    return None, None


def runtime_failure_detail(case: E2EEvalCase, exc: Exception) -> dict[str, Any]:
    checks = {
        "runtime_pass": False,
        "parser_symptom_hit": False,
        "normalizer_expansion_hit": False,
        "triage_correct": False,
        "retrieval_hit_at_5_title": False,
        "retrieval_hit_at_5_section_type": False,
        "answer_context_has_expected_title": False,
        "min_answerable_chunks_pass": False,
        "citation_requirement_pass": False,
        "disclaimer_requirement_pass": False,
        "safe_escalation_pass": False,
        "must_include_pass": False,
        "must_include_any_pass": False,
        "must_not_include_pass": False,
        "safety_pass": False,
    }
    return {
        "id": case.id,
        "input": case.input,
        "passed": False,
        "failure_stage": "runtime_error",
        "reason": f"{type(exc).__name__}: {exc}",
        "checks": checks,
        "triage_level": None,
        "expected_triage_level": case.expected_triage_level,
        "parsed_symptoms": [],
        "expanded_terms": [],
        "top_titles": [],
        "top_section_types": [],
        "answer_context_titles": [],
        "answer_context_section_types": [],
        "answerable_chunks": 0,
        "low_value_answer_context_chunks": 0,
        "citation_count": 0,
        "safety": {},
    }


def build_answer_text(final_output: dict[str, Any]) -> str:
    parts = [
        str(final_output.get("user_summary", "")),
        str(final_output.get("recommendation", "")),
        " ".join(str(item) for item in final_output.get("care_advice", [])),
        " ".join(str(item) for item in final_output.get("red_flags", [])),
        str(final_output.get("when_to_seek_help", "")),
        " ".join(str(item) for item in final_output.get("related_health_topics", [])),
        str(final_output.get("safety_disclaimer", "")),
    ]
    return normalize_text(" ".join(parts))


def safe_escalation_pass(case: E2EEvalCase, answer_text: str) -> bool:
    if not case.requires_safe_escalation:
        return True
    if case.expected_triage_level == "emergency":
        return contains_any_text(answer_text, ["cấp cứu", "khẩn cấp", "gọi cấp cứu"])
    if case.expected_triage_level == "urgent_visit":
        return contains_any_text(answer_text, ["khám sớm", "đánh giá sớm", "đi khám"])
    return True


def count_answerable(hits: list[RetrievalHit]) -> int:
    return sum(1 for hit in hits if hit.section_type not in LOW_VALUE_SECTION_TYPES)


def matches_any(values: list[str], expected_any: list[str]) -> bool:
    if not expected_any:
        return True
    return any(text_matches(value, expected) for value in values for expected in expected_any)


def matches_any_text(text: str, expected_any: list[str]) -> bool:
    if not expected_any:
        return True
    return contains_any_text(text, expected_any)


def all_contains(text: str, required_terms: list[str]) -> bool:
    return all(normalize_text(term) in text for term in required_terms)


def contains_any_text(text: str, terms: list[str]) -> bool:
    return any(normalize_text(term) in text for term in terms)


def text_matches(value: str, expected: str) -> bool:
    value_norm = normalize_text(value)
    expected_norm = normalize_text(expected)
    return value_norm == expected_norm or expected_norm in value_norm or value_norm in expected_norm


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def failure_stage_counts(details: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for detail in details:
        stage = detail.get("failure_stage")
        if stage:
            counts[stage] = counts.get(stage, 0) + 1
    return counts


def load_cases(path: str | Path) -> list[E2EEvalCase]:
    cases: list[E2EEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                cases.append(E2EEvalCase.model_validate(json.loads(line)))
    return cases


def write_report(metrics: dict[str, Any], report_path: Path, failures_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    metrics["report_path"] = str(report_path)
    metrics["failures_path"] = str(failures_path)
    report_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [detail for detail in metrics.get("details", []) if not detail.get("passed", False)]
    with failures_path.open("w", encoding="utf-8") as file:
        for failure in failures:
            file.write(json.dumps(failure, ensure_ascii=False) + "\n")


def _mean_check(details: list[dict[str, Any]], check_name: str) -> float:
    return _mean([detail["checks"].get(check_name, False) for detail in details])


def _mean(values: list[float | bool]) -> float:
    return sum(float(value) for value in values) / len(values) if values else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--vector-top-k", type=int, default=30)
    parser.add_argument("--bm25-top-k", type=int, default=30)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--failures-path", type=Path, default=DEFAULT_FAILURES_PATH)
    return parser.parse_args()


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
