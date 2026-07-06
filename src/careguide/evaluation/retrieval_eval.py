from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from careguide.agents.retriever import HybridRetrieverAgent
from careguide.schemas.retrieval import RetrievalMode, RetrievalResult


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = ROOT / "data" / "test_cases" / "retrieval_eval_cases.jsonl"
LOW_VALUE_SECTION_TYPES = {"metadata", "aliases"}


class RetrievalEvalCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expanded_terms: list[str] = Field(default_factory=list)
    expected_titles_any: list[str] = Field(default_factory=list)
    expected_sources_any: list[str] = Field(default_factory=list)
    expected_section_types_any: list[str] = Field(default_factory=list)


def main() -> None:
    _configure_stdout()
    args = _parse_args()
    cases = load_cases(args.cases)
    retriever = HybridRetrieverAgent()
    metrics = evaluate_retrieval_cases(
        cases=cases,
        retriever=retriever,
        top_k=args.top_k,
        mode=args.mode,
        vector_top_k=args.vector_top_k,
        bm25_top_k=args.bm25_top_k,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def evaluate_retrieval_cases(
    cases: list[RetrievalEvalCase],
    retriever: HybridRetrieverAgent,
    top_k: int = 5,
    mode: RetrievalMode = "hybrid",
    vector_top_k: int = 30,
    bm25_top_k: int = 30,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []

    for case in cases:
        result = retriever.run(
            query=case.query,
            expanded_terms=case.expanded_terms,
            top_k=top_k,
            mode=mode,
            vector_top_k=vector_top_k,
            bm25_top_k=bm25_top_k,
        )
        details.append(evaluate_retrieval_result(case, result))

    return aggregate_retrieval_metrics(details)


def evaluate_retrieval_result(case: RetrievalEvalCase, result: RetrievalResult) -> dict[str, Any]:
    title_rank = first_matching_rank([hit.title for hit in result.results], case.expected_titles_any)
    source_rank = first_matching_rank([hit.source for hit in result.results], case.expected_sources_any)
    section_rank = first_matching_rank([hit.section_type for hit in result.results], case.expected_section_types_any)
    low_value_count = sum(1 for hit in result.results if hit.section_type in LOW_VALUE_SECTION_TYPES)
    result_count = len(result.results)

    return {
        "id": case.id,
        "query": case.query,
        "top_titles": [hit.title for hit in result.results],
        "top_sources": [hit.source for hit in result.results],
        "top_section_types": [hit.section_type for hit in result.results],
        "hit_title": title_rank is not None,
        "hit_source": source_rank is not None,
        "hit_section_type": section_rank is not None,
        "title_rank": title_rank,
        "source_rank": source_rank,
        "section_type_rank": section_rank,
        "mrr_title": 1.0 / title_rank if title_rank else 0.0,
        "top_score": result.results[0].final_score if result.results else 0.0,
        "answerable_chunks_at_5": result_count - low_value_count,
        "low_value_section_rate_at_5": low_value_count / result_count if result_count else 0.0,
    }


def aggregate_retrieval_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(details)
    if total == 0:
        return {"total": 0, "details": []}

    return {
        "total": total,
        "hit_at_5_title": _mean([detail["hit_title"] for detail in details]),
        "hit_at_5_source": _mean([detail["hit_source"] for detail in details]),
        "hit_at_5_section_type": _mean([detail["hit_section_type"] for detail in details]),
        "mrr_title": _mean([detail["mrr_title"] for detail in details]),
        "avg_top_score": _mean([detail["top_score"] for detail in details]),
        "avg_answerable_chunks_at_5": _mean([detail["answerable_chunks_at_5"] for detail in details]),
        "avg_low_value_section_rate_at_5": _mean([detail["low_value_section_rate_at_5"] for detail in details]),
        "details": details,
    }


def first_matching_rank(values: list[str], expected_any: list[str]) -> int | None:
    if not expected_any:
        return None

    expected = {normalize_text(item) for item in expected_any}
    for index, value in enumerate(values, start=1):
        if normalize_text(value) in expected:
            return index
    return None


def load_cases(path: str | Path) -> list[RetrievalEvalCase]:
    cases: list[RetrievalEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                cases.append(RetrievalEvalCase.model_validate(json.loads(line)))
    return cases


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _mean(values: list[float | bool]) -> float:
    return sum(float(value) for value in values) / len(values) if values else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--vector-top-k", type=int, default=30)
    parser.add_argument("--bm25-top-k", type=int, default=30)
    return parser.parse_args()


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
