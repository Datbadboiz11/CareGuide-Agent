from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable
from typing import Any

from careguide.agents.answer import AnswerAgent, LOW_VALUE_SECTION_TYPES
from careguide.agents.normalizer import MedicalTermNormalizerAgent
from careguide.agents.red_flag import RedFlagAgent
from careguide.agents.retriever import HybridRetrieverAgent, build_expanded_terms
from careguide.agents.symptom_parser import SymptomParserAgent
from careguide.agents.triage import TriageAgent
from careguide.graph.state import CareGuideState
from careguide.schemas.retrieval import RetrievalHit, RetrievalMode, RetrievalResult

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


DEFAULT_TOP_K = 5
DEFAULT_VECTOR_TOP_K = 30
DEFAULT_BM25_TOP_K = 30
MIN_ANSWERABLE_CONTEXT = 3

DIAGNOSIS_CLAIMS = (
    "bạn chắc chắn bị",
    "chắc chắn bạn bị",
    "bạn bị nhồi máu cơ tim",
    "chẩn đoán là",
    "diagnosis is",
)
PRESCRIBING_CLAIMS = (
    "uống kháng sinh",
    "liều",
    " mg",
    "milligram",
)
EMERGENCY_ESCALATION_TERMS = (
    "cấp cứu",
    "khẩn cấp",
    "gọi cấp cứu",
    "đến cơ sở y tế",
    "cáº¥p cá»©u",
    "kháº©n cáº¥p",
)


class LinearCompiledGraph:

    def __init__(self, nodes: list[Callable[[CareGuideState], dict[str, Any]]]) -> None:
        self.nodes = nodes

    def invoke(self, state: CareGuideState) -> CareGuideState:
        current = dict(state)
        for node in self.nodes:
            current.update(node(current))
        return current


class CareGuideGraph:

    def __init__(
        self,
        parser_agent: SymptomParserAgent | None = None,
        normalizer_agent: MedicalTermNormalizerAgent | None = None,
        red_flag_agent: RedFlagAgent | None = None,
        triage_agent: TriageAgent | None = None,
        retriever_agent: HybridRetrieverAgent | None = None,
        answer_agent: AnswerAgent | None = None,
        top_k: int = DEFAULT_TOP_K,
        vector_top_k: int = DEFAULT_VECTOR_TOP_K,
        bm25_top_k: int = DEFAULT_BM25_TOP_K,
        retrieval_mode: RetrievalMode = "hybrid",
    ) -> None:
        self.parser_agent = parser_agent or SymptomParserAgent()
        self.normalizer_agent = normalizer_agent or MedicalTermNormalizerAgent()
        self.red_flag_agent = red_flag_agent or RedFlagAgent()
        self.triage_agent = triage_agent or TriageAgent()
        self.retriever_agent = retriever_agent or HybridRetrieverAgent()
        self.answer_agent = answer_agent or AnswerAgent()
        self.top_k = top_k
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.retrieval_mode = retrieval_mode
        self._compiled_graph: Any | None = None

    def compile(self) -> Any:
        if self._compiled_graph is None:
            self._compiled_graph = self._build_graph()
        return self._compiled_graph

    def run(self, raw_input: str) -> CareGuideState:
        return self.compile().invoke({"raw_input": raw_input, "errors": []})

    def parse_symptoms_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"parsed": self.parser_agent.run(state["raw_input"])}

    def normalize_terms_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"normalized": self.normalizer_agent.run(state["parsed"])}

    def detect_red_flags_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"red_flags": self.red_flag_agent.run(state["parsed"], state["normalized"])}

    def triage_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"triage": self.triage_agent.run(state["parsed"], state["normalized"], state["red_flags"])}

    def build_retrieval_query_node(self, state: CareGuideState) -> dict[str, Any]:
        expanded_terms = build_graph_expanded_terms(state)
        return {
            "retrieval_query": build_positive_retrieval_query(state),
            "expanded_terms": expanded_terms,
        }

    def retrieve_context_node(self, state: CareGuideState) -> dict[str, Any]:
        retrieval = self.retriever_agent.run(
            query=state["retrieval_query"],
            expanded_terms=state.get("expanded_terms", []),
            top_k=self.top_k,
            mode=self.retrieval_mode,
            vector_top_k=self.vector_top_k,
            bm25_top_k=self.bm25_top_k,
            triage_level=state["triage"].triage_level,
        )
        return {"retrieval": retrieval}

    def select_answer_context_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"answer_context": select_answer_context(state["retrieval"].results, self.top_k)}

    def generate_answer_node(self, state: CareGuideState) -> dict[str, Any]:
        retrieval = state["retrieval"].model_copy(update={"results": state["answer_context"]})
        answer = self.answer_agent.run(state["parsed"], state["triage"], state["red_flags"], retrieval)
        return {"answer": answer}

    def safety_check_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"safety": run_safety_check(state)}

    def build_final_output_node(self, state: CareGuideState) -> dict[str, Any]:
        return {"final_output": build_final_output(state)}

    def _build_graph(self) -> Any:
        nodes = [
            self.parse_symptoms_node,
            self.normalize_terms_node,
            self.detect_red_flags_node,
            self.triage_node,
            self.build_retrieval_query_node,
            self.retrieve_context_node,
            self.select_answer_context_node,
            self.generate_answer_node,
            self.safety_check_node,
            self.build_final_output_node,
        ]
        if not LANGGRAPH_AVAILABLE:
            return LinearCompiledGraph(nodes)

        graph = StateGraph(CareGuideState)
        graph.add_node("parse_symptoms", self.parse_symptoms_node)
        graph.add_node("normalize_terms", self.normalize_terms_node)
        graph.add_node("detect_red_flags", self.detect_red_flags_node)
        graph.add_node("triage", self.triage_node)
        graph.add_node("build_retrieval_query", self.build_retrieval_query_node)
        graph.add_node("retrieve_context", self.retrieve_context_node)
        graph.add_node("select_answer_context", self.select_answer_context_node)
        graph.add_node("generate_answer", self.generate_answer_node)
        graph.add_node("safety_check", self.safety_check_node)
        graph.add_node("build_final_output", self.build_final_output_node)

        graph.add_edge(START, "parse_symptoms")
        graph.add_edge("parse_symptoms", "normalize_terms")
        graph.add_edge("normalize_terms", "detect_red_flags")
        graph.add_edge("detect_red_flags", "triage")
        graph.add_edge("triage", "build_retrieval_query")
        graph.add_edge("build_retrieval_query", "retrieve_context")
        graph.add_edge("retrieve_context", "select_answer_context")
        graph.add_edge("select_answer_context", "generate_answer")
        graph.add_edge("generate_answer", "safety_check")
        graph.add_edge("safety_check", "build_final_output")
        graph.add_edge("build_final_output", END)
        return graph.compile()


def build_graph_expanded_terms(state: CareGuideState) -> list[str]:
    terms: list[str] = []
    terms.extend(build_expanded_terms(state["raw_input"]))

    normalized = state.get("normalized")
    if normalized:
        terms.extend(symptom.canonical for symptom in normalized.normalized_symptoms if not symptom.negated)

    red_flags = state.get("red_flags")
    if red_flags:
        for finding in red_flags.red_flags:
            if finding.canonical:
                terms.append(finding.canonical)
            terms.append(finding.name)

    triage = state.get("triage")
    if triage:
        terms.extend(triage.red_flags)
        if triage.requires_emergency:
            terms.append("medical emergency")
        elif triage.requires_urgent:
            terms.append("urgent medical advice")

    excluded_terms = negated_expanded_terms(state)
    filtered_terms = [term for term in dedupe_terms(terms) if term not in excluded_terms]
    return build_expanded_terms("", filtered_terms)


def negated_expanded_terms(state: CareGuideState) -> set[str]:
    normalized = state.get("normalized")
    if not normalized:
        return set()

    terms: list[str] = []
    for symptom in normalized.normalized_symptoms:
        if not symptom.negated:
            continue
        terms.append(symptom.canonical)
        terms.extend(build_expanded_terms(symptom.original))
        terms.extend(build_expanded_terms(symptom.canonical))
    return set(dedupe_terms(terms))


def build_positive_retrieval_query(state: CareGuideState) -> str:
    raw_query = state["raw_input"].strip()
    parsed = state.get("parsed")
    if not parsed:
        return raw_query

    if parsed.negated_symptoms:
        positive_query = build_positive_only_query(parsed)
        if positive_query:
            return positive_query

    query = raw_query
    negated_terms = list(parsed.negated_symptoms)
    normalized = state.get("normalized")
    if normalized:
        negated_terms.extend(symptom.original for symptom in normalized.normalized_symptoms if symptom.negated)

    for term in dedupe_terms(negated_terms):
        query = remove_negated_term(query, term)

    cleaned = normalize_spacing(query)
    if cleaned:
        return cleaned

    positive_parts: list[str] = []
    positive_parts.extend(parsed.symptoms)
    if parsed.duration:
        positive_parts.append(parsed.duration)
    positive_parts.extend(parsed.severity)
    positive_parts.extend(parsed.risk_factors)
    for key, value in parsed.vitals.items():
        positive_parts.append(f"{key} {value}")
    fallback = " ".join(part for part in positive_parts if part).strip()
    return fallback or raw_query


def build_positive_only_query(parsed: Any) -> str:
    parts: list[str] = []
    parts.extend(parsed.symptoms)
    parts.extend(parsed.severity)
    parts.extend(parsed.risk_factors)
    if parsed.duration:
        parts.append(parsed.duration)
    for key, value in parsed.vitals.items():
        parts.append(f"{key} {value}")
    return " ".join(dedupe_terms(part for part in parts if part))


def remove_negated_term(text: str, term: str) -> str:
    normalized_term = re.escape(term.strip())
    if not normalized_term:
        return text
    pattern = re.compile(
        rf"(?i)(?:,?\s*)\b(?:không|khong|chưa|chua)\s+(?:bị\s+|bi\s+|có\s+|co\s+)?{normalized_term}\b"
    )
    return pattern.sub("", text)


def normalize_spacing(text: str) -> str:
    cleaned = re.sub(r"\s+([,.])", r"\1", text)
    cleaned = re.sub(r"([,.]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,.")


def select_answer_context(
    hits: list[RetrievalHit],
    top_k: int = DEFAULT_TOP_K,
    min_answerable: int = MIN_ANSWERABLE_CONTEXT,
) -> list[RetrievalHit]:
    answerable = [hit for hit in hits if hit.section_type not in LOW_VALUE_SECTION_TYPES]
    if len(answerable) >= min_answerable:
        return answerable[:top_k]
    low_value = [hit for hit in hits if hit.section_type in LOW_VALUE_SECTION_TYPES]
    return (answerable + low_value)[:top_k]


def run_safety_check(state: CareGuideState) -> dict[str, Any]:
    answer = state["answer"]
    triage = state["triage"]
    answer_text = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False).lower()
    requires_citation = bool(state.get("answer_context")) or triage.triage_level != "self_care"

    checks = {
        "no_definitive_diagnosis": not contains_any(answer_text, DIAGNOSIS_CLAIMS),
        "no_prescribing_or_dosage": not contains_any(answer_text, PRESCRIBING_CLAIMS),
        "emergency_escalation_present": (
            contains_any(answer_text, EMERGENCY_ESCALATION_TERMS)
            if triage.triage_level == "emergency"
            else True
        ),
        "disclaimer_present": bool(answer.safety_disclaimer),
        "citation_requirement_pass": (bool(answer.citations) if requires_citation else True),
    }
    return {
        "requires_citation": requires_citation,
        "passed": all(checks.values()),
        "checks": checks,
    }


def build_final_output(state: CareGuideState) -> dict[str, Any]:
    answer = state["answer"]
    return {
        "triage_level": answer.triage_level,
        "confidence": answer.confidence,
        "user_summary": answer.user_summary,
        "recommendation": answer.recommendation,
        "care_advice": answer.care_advice,
        "red_flags": answer.red_flags,
        "when_to_seek_help": answer.when_to_seek_help,
        "related_health_topics": answer.related_health_topics,
        "citations": [citation.model_dump(mode="json") for citation in answer.citations],
        "safety_disclaimer": answer.safety_disclaimer,
        "safety": state["safety"],
    }


def run_careguide(raw_input: str, graph: CareGuideGraph | None = None) -> CareGuideState:
    return (graph or CareGuideGraph()).run(raw_input)


def dedupe_terms(terms: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = " ".join(str(term).lower().strip().split())
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    graph = CareGuideGraph(retrieval_mode=args.mode, top_k=args.top_k)
    result = graph.run(args.input)
    print(json.dumps(serialize_state(result), ensure_ascii=False, indent=2))


def serialize_state(state: CareGuideState) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in state.items():
        if hasattr(value, "model_dump"):
            serialized[key] = value.model_dump(mode="json")
        elif isinstance(value, list):
            serialized[key] = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        else:
            serialized[key] = value
    return serialized


if __name__ == "__main__":
    main()
