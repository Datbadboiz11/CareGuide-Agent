from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from careguide.schemas.retrieval import RetrievalHit, RetrievalMode, RetrievalResult


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INDEX_DIR = ROOT / "data" / "indexes"
DEFAULT_FAISS_PATH = DEFAULT_INDEX_DIR / "official_rag_faiss.index"
DEFAULT_METADATA_PATH = DEFAULT_INDEX_DIR / "official_rag_chunk_metadata.jsonl"
DEFAULT_MANIFEST_PATH = DEFAULT_INDEX_DIR / "official_rag_index_manifest.json"
DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-base"

RRF_K = 60
VECTOR_WEIGHT = 0.65
BM25_WEIGHT = 0.35
EXPANDED_VECTOR_WEIGHT = 0.45
EXPANDED_BM25_WEIGHT = 0.55
TITLE_TOPIC_BONUS = 0.002
SECTION_BONUS = {
    "immediate_action": 0.004,
    "urgent_advice": 0.004,
    "when_to_get_help": 0.003,
    "emergency": 0.003,
    "symptoms": 0.002,
    "overview": 0.001,
}
FLU_RESPIRATORY_COMBO_EXPANSIONS = [
    "flu",
    "influenza",
    "flu symptoms",
    "respiratory tract infection",
    "upper respiratory infection",
    "viral respiratory infection",
]
COMMON_COLD_COMBO_EXPANSIONS = [
    "common cold",
    "cold symptoms",
    "upper respiratory infection",
    "respiratory tract infection",
]
ROUTINE_SECTION_BONUS = {
    "symptoms": 0.003,
    "overview": 0.002,
    "self_care": 0.003,
    "non_urgent_advice": 0.002,
    "treatment": 0.001,
}
LOW_VALUE_SECTION_PENALTY = {
    "metadata": 0.004,
    "aliases": 0.004,
}
EMERGENCY_TERMS = {
    "anaphylaxis",
    "arm weakness",
    "carbon monoxide",
    "chest pain",
    "confusion",
    "difficulty breathing",
    "emergency",
    "face drooping",
    "heart attack",
    "heat stroke",
    "meningitis",
    "one-sided weakness",
    "seizure",
    "sepsis",
    "severe difficulty breathing",
    "shortness of breath",
    "speech difficulty",
    "stroke",
    "swollen lips",
    "trouble speaking",
    "vomiting blood",
    "weakness",
    "co giật",
    "cứng cổ",
    "đau ngực",
    "khó thở",
    "lơ mơ",
    "méo miệng",
    "nói khó",
    "nôn ra máu",
    "sưng môi",
    "yếu một bên",
}
QUERY_EXPANSIONS = {
    "hải sản": ["seafood allergy", "food allergy", "anaphylaxis"],
    "sưng môi": ["swollen lips", "anaphylaxis", "serious allergic reaction"],
    "nổi mề đay": ["hives", "urticaria", "anaphylaxis", "allergic reaction"],
    "méo miệng": ["face drooping", "facial drooping", "stroke", "FAST stroke symptoms"],
    "yếu một bên": ["one-sided weakness", "arm weakness", "leg weakness", "stroke symptoms"],
    "nói khó": ["speech difficulty", "slurred speech", "trouble speaking", "stroke"],
    "sốt": ["fever", "high temperature"],
    "rét run": ["chills", "shivering", "sepsis", "infection"],
    "nhiễm trùng": ["infection", "sepsis"],
    "cứng cổ": ["stiff neck", "meningitis"],
    "lơ mơ": ["confusion", "altered mental status", "sepsis", "meningitis"],
    "ho": ["cough"],
    "đau họng": ["sore throat"],
    "amidan": ["tonsils", "swollen tonsils", "strep throat"],
    "không ho": ["strep throat", "sore throat without cough"],
    "đau người": ["body aches", "muscle aches"],
    "cúm": ["flu", "influenza"],
    "covid": ["COVID-19", "coronavirus"],
    "mất mùi": ["loss of smell", "COVID-19", "coronavirus"],
    "khó thở": ["shortness of breath", "difficulty breathing"],
    "đau ngực": ["chest pain", "heart attack"],
    "đau ngực khi thở": ["pneumonia", "chest pain when breathing", "pleurisy"],
    "hen": ["asthma", "asthma attack", "inhaler"],
    "thuốc xịt": ["inhaler", "asthma reliever inhaler"],
    "co giật": ["seizure", "convulsion"],
    "nôn ra máu": ["vomiting blood"],
    "tiêu chảy": ["diarrhea"],
    "mất nước": ["dehydration"],
    "vùng nhiệt đới": ["tropical travel", "dengue", "dengue fever"],
    "chảy máu chân răng": ["bleeding gums", "dengue", "severe dengue"],
    "ngoài nắng": ["heat illness", "heat exhaustion", "heat stroke"],
    "say nắng": ["heat illness", "heat exhaustion", "heat stroke"],
    "buồn nôn": ["nausea"],
    "bỏng": ["burn", "burns and scalds"],
    "nước sôi": ["scald", "burns and scalds"],
    "phồng rộp": ["blisters", "burn"],
    "ngã đập đầu": ["head injury", "traumatic brain injury", "concussion"],
    "lú lẫn": ["confusion", "altered mental status", "head injury", "sepsis"],
    "mang thai": ["pregnancy"],
    "ra máu âm đạo": ["vaginal bleeding", "pregnancy bleeding", "ectopic pregnancy"],
    "tiểu đường": ["diabetes", "blood glucose", "hypoglycemia"],
    "run tay": ["shaking", "hypoglycemia", "low blood glucose"],
    "vã mồ hôi": ["sweating", "hypoglycemia", "low blood glucose"],
    "chóng mặt": ["dizziness"],
    "bếp gas": ["gas", "carbon monoxide poisoning"],
    "phòng kín": ["carbon monoxide poisoning"],
}


@dataclass(frozen=True)
class RankedItem:

    index: int
    rank: int
    score: float


class SimpleBM25:

    def __init__(
        self,
        tokenized_documents: list[list[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.documents = tokenized_documents
        self.k1 = k1
        self.b = b
        self.doc_count = len(tokenized_documents)
        self.doc_lengths = [len(document) for document in tokenized_documents]
        self.avg_doc_length = sum(self.doc_lengths) / self.doc_count if self.doc_count else 0.0
        self.term_frequencies = [_term_counts(document) for document in tokenized_documents]
        self.idf = self._build_idf()

    def search(self, query: str, top_k: int) -> list[RankedItem]:
        tokens = tokenize(query)
        if not tokens or top_k <= 0:
            return []

        scores = [self._score_document(tokens, index) for index in range(self.doc_count)]
        ranked = [
            RankedItem(index=index, rank=rank, score=score)
            for rank, (index, score) in enumerate(
                sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k],
                start=1,
            )
            if score > 0
        ]
        return ranked

    def _build_idf(self) -> dict[str, float]:
        document_frequency: dict[str, int] = {}
        for document in self.documents:
            for token in set(document):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        idf: dict[str, float] = {}
        for token, frequency in document_frequency.items():
            idf[token] = math.log(1 + (self.doc_count - frequency + 0.5) / (frequency + 0.5))
        return idf

    def _score_document(self, query_tokens: list[str], index: int) -> float:
        score = 0.0
        frequencies = self.term_frequencies[index]
        doc_length = self.doc_lengths[index]

        for token in query_tokens:
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
            score += self.idf.get(token, 0.0) * frequency * (self.k1 + 1) / denominator

        return score


class HybridRetrieverAgent:

    def __init__(
        self,
        faiss_path: str | Path = DEFAULT_FAISS_PATH,
        metadata_path: str | Path = DEFAULT_METADATA_PATH,
        manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
        model_name: str | None = None,
        vector_weight: float = VECTOR_WEIGHT,
        bm25_weight: float = BM25_WEIGHT,
        rrf_k: int = RRF_K,
    ) -> None:
        self.faiss_path = Path(faiss_path)
        self.metadata_path = Path(metadata_path)
        self.manifest_path = Path(manifest_path)
        self.manifest = load_manifest(self.manifest_path)
        self.model_name = model_name or self.manifest.get("model_name") or DEFAULT_MODEL_NAME
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self.metadata = load_metadata(self.metadata_path)
        self.bm25 = SimpleBM25([tokenize(metadata_to_bm25_text(item)) for item in self.metadata])
        self._faiss_index: Any | None = None
        self._model: Any | None = None

    def run(
        self,
        query: str,
        top_k: int = 5,
        mode: RetrievalMode = "hybrid",
        expanded_terms: Iterable[str] | None = None,
        vector_top_k: int = 30,
        bm25_top_k: int = 30,
        triage_level: str | None = None,
    ) -> RetrievalResult:
        expanded_term_list = build_expanded_terms(query, expanded_terms)
        expanded_query = build_expanded_query(query, expanded_term_list)
        vector_items: list[RankedItem] = []
        bm25_items: list[RankedItem] = []

        if mode in {"vector", "hybrid"}:
            vector_items = self.vector_search(query, vector_top_k if mode == "hybrid" else top_k)

        if mode in {"bm25", "hybrid"}:
            bm25_items = self.bm25.search(expanded_query, bm25_top_k if mode == "hybrid" else top_k)

        if mode == "vector":
            hits = hits_from_single_ranker(vector_items, self.metadata, "vector", top_k)
        elif mode == "bm25":
            hits = hits_from_single_ranker(bm25_items, self.metadata, "bm25", top_k)
        else:
            vector_weight, bm25_weight = fusion_weights(expanded_term_list, self.vector_weight, self.bm25_weight)
            hits = weighted_rrf_fusion(
                metadata=self.metadata,
                vector_items=vector_items,
                bm25_items=bm25_items,
                top_k=top_k,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
                rrf_k=self.rrf_k,
                expanded_terms=expanded_term_list,
                apply_urgent_section_bonus=should_apply_urgent_section_bonus(
                    query,
                    expanded_term_list,
                    triage_level,
                ),
                triage_level=triage_level,
            )

        return RetrievalResult(
            query=query,
            expanded_query=expanded_query if expanded_query != query else None,
            mode=mode,
            top_k=top_k,
            vector_top_k=len(vector_items),
            bm25_top_k=len(bm25_items),
            results=hits,
        )

    def vector_search(self, query: str, top_k: int) -> list[RankedItem]:
        if top_k <= 0:
            return []

        index = self._load_faiss_index()
        model = self._load_model()
        query_embedding = model.encode(
            [f"query: {query}"],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")

        scores, indices = index.search(query_embedding, min(top_k, len(self.metadata)))
        return [
            RankedItem(index=int(index_value), rank=rank, score=float(score))
            for rank, (index_value, score) in enumerate(zip(indices[0], scores[0]), start=1)
            if int(index_value) >= 0
        ]

    def _load_faiss_index(self) -> Any:
        if self._faiss_index is None:
            import faiss

            self._faiss_index = faiss.read_index(str(self.faiss_path))
            if self._faiss_index.ntotal != len(self.metadata):
                raise ValueError(
                    f"FAISS index count {self._faiss_index.ntotal} does not match metadata count {len(self.metadata)}"
                )
        return self._faiss_index

    def _load_model(self) -> Any:
        if self._model is None:
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model


def weighted_rrf_fusion(
    metadata: list[dict[str, Any]],
    vector_items: list[RankedItem],
    bm25_items: list[RankedItem],
    top_k: int,
    vector_weight: float = VECTOR_WEIGHT,
    bm25_weight: float = BM25_WEIGHT,
    rrf_k: int = RRF_K,
    expanded_terms: Iterable[str] | None = None,
    apply_urgent_section_bonus: bool = True,
    triage_level: str | None = None,
) -> list[RetrievalHit]:
    candidates: dict[int, dict[str, Any]] = {}

    for item in vector_items:
        candidate = candidates.setdefault(item.index, {"index": item.index})
        candidate["vector_rank"] = item.rank
        candidate["vector_score"] = item.score

    for item in bm25_items:
        candidate = candidates.setdefault(item.index, {"index": item.index})
        candidate["bm25_rank"] = item.rank
        candidate["bm25_score"] = item.score

    scored: list[dict[str, Any]] = []
    for candidate in candidates.values():
        item_metadata = metadata[candidate["index"]]
        bonus = section_bonus(item_metadata.get("section_type", ""), apply_urgent_section_bonus, triage_level)
        title_bonus = title_topic_bonus(item_metadata, expanded_terms)
        penalty = low_value_section_penalty(item_metadata.get("section_type", ""))
        score = 0.0
        if candidate.get("vector_rank") is not None:
            score += vector_weight * reciprocal_rank(candidate["vector_rank"], rrf_k)
        if candidate.get("bm25_rank") is not None:
            score += bm25_weight * reciprocal_rank(candidate["bm25_rank"], rrf_k)
        score += bonus
        score += title_bonus
        score -= penalty
        candidate["final_score"] = score
        candidate["section_bonus"] = bonus
        candidate["title_topic_bonus"] = title_bonus
        candidate["low_value_section_penalty"] = penalty
        scored.append(candidate)

    scored.sort(key=lambda item: item["final_score"], reverse=True)
    return [
        hit_from_candidate(rank, candidate, metadata[candidate["index"]])
        for rank, candidate in enumerate(scored[:top_k], start=1)
    ]


def hits_from_single_ranker(
    items: list[RankedItem],
    metadata: list[dict[str, Any]],
    ranker: str,
    top_k: int,
) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    for rank, item in enumerate(items[:top_k], start=1):
        candidate: dict[str, Any] = {
            "index": item.index,
            "final_score": item.score,
            "section_bonus": 0.0,
            "title_topic_bonus": 0.0,
            "low_value_section_penalty": 0.0,
        }
        if ranker == "vector":
            candidate["vector_rank"] = item.rank
            candidate["vector_score"] = item.score
        else:
            candidate["bm25_rank"] = item.rank
            candidate["bm25_score"] = item.score
        hits.append(hit_from_candidate(rank, candidate, metadata[item.index]))
    return hits


def hit_from_candidate(rank: int, candidate: dict[str, Any], metadata: dict[str, Any]) -> RetrievalHit:
    return RetrievalHit(
        rank=rank,
        chunk_id=metadata["chunk_id"],
        document_id=metadata["document_id"],
        source=metadata["source"],
        url=metadata["url"],
        title=metadata["title"],
        topic=metadata["topic"],
        section_heading=metadata["section_heading"],
        section_type=metadata["section_type"],
        text=metadata["text"],
        final_score=float(candidate["final_score"]),
        vector_rank=candidate.get("vector_rank"),
        bm25_rank=candidate.get("bm25_rank"),
        vector_score=candidate.get("vector_score"),
        bm25_score=candidate.get("bm25_score"),
        section_bonus=float(candidate.get("section_bonus", 0.0)),
        title_topic_bonus=float(candidate.get("title_topic_bonus", 0.0)),
        low_value_section_penalty=float(candidate.get("low_value_section_penalty", 0.0)),
    )


def reciprocal_rank(rank: int, rrf_k: int = RRF_K) -> float:
    if rank < 1:
        raise ValueError("rank must start from 1")
    return 1.0 / (rrf_k + rank)


def section_bonus(
    section_type: str,
    apply_urgent_bonus: bool = True,
    triage_level: str | None = None,
) -> float:
    if triage_level in {"routine_visit", "self_care"}:
        return ROUTINE_SECTION_BONUS.get(section_type, 0.0)
    if section_type in {"immediate_action", "urgent_advice", "when_to_get_help", "emergency"}:
        return SECTION_BONUS.get(section_type, 0.0) if apply_urgent_bonus else 0.0
    return SECTION_BONUS.get(section_type, 0.0)


def low_value_section_penalty(section_type: str) -> float:
    return LOW_VALUE_SECTION_PENALTY.get(section_type, 0.0)


def title_topic_bonus(metadata: dict[str, Any], expanded_terms: Iterable[str] | None = None) -> float:
    terms = [normalize_query_term(term) for term in expanded_terms or []]
    terms = [term for term in terms if len(term) >= 3]
    if not terms:
        return 0.0

    title = normalize_query_term(str(metadata.get("title", "")))
    topic = normalize_query_term(str(metadata.get("topic", "")))
    matched = 0
    if any(term in title for term in terms):
        matched += 1
    if any(term in topic for term in terms):
        matched += 1
    return TITLE_TOPIC_BONUS * matched


def fusion_weights(
    expanded_terms: Iterable[str],
    default_vector_weight: float = VECTOR_WEIGHT,
    default_bm25_weight: float = BM25_WEIGHT,
) -> tuple[float, float]:
    terms = [term for term in expanded_terms if term]
    if len(terms) >= 2:
        return EXPANDED_VECTOR_WEIGHT, EXPANDED_BM25_WEIGHT
    if len(terms) == 1:
        return 0.60, 0.40
    return default_vector_weight, default_bm25_weight


def has_emergency_terms(query: str, expanded_terms: Iterable[str] | None = None) -> bool:
    text = normalize_query_term(build_expanded_query(query, expanded_terms))
    return any(contains_query_marker(text, term) for term in EMERGENCY_TERMS)


def should_apply_urgent_section_bonus(
    query: str,
    expanded_terms: Iterable[str] | None = None,
    triage_level: str | None = None,
) -> bool:
    if triage_level in {"emergency", "urgent_visit"}:
        return True
    if triage_level in {"routine_visit", "self_care"}:
        return False
    return has_emergency_terms(query, expanded_terms)


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {"model_name": DEFAULT_MODEL_NAME}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_metadata(path: str | Path) -> list[dict[str, Any]]:
    metadata_path = Path(path)
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing retrieval metadata file: {metadata_path}")

    items: list[dict[str, Any]] = []
    with metadata_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            validate_metadata_item(item, metadata_path, line_number)
            items.append(item)
    return items


def validate_metadata_item(item: dict[str, Any], path: Path, line_number: int) -> None:
    required = {
        "chunk_id",
        "document_id",
        "source",
        "url",
        "title",
        "topic",
        "section_heading",
        "section_type",
        "text",
    }
    missing = required - set(item)
    if missing:
        raise ValueError(f"{path}:{line_number}: missing fields {sorted(missing)}")


def metadata_to_bm25_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(field, ""))
        for field in ("title", "topic", "section_heading", "section_type", "text")
    )


def build_expanded_query(query: str, expanded_terms: Iterable[str] | None = None) -> str:
    terms = [query]
    if expanded_terms:
        terms.extend(term for term in expanded_terms if term)
    return " ".join(terms).strip()


def build_expanded_terms(query: str, expanded_terms: Iterable[str] | None = None) -> list[str]:
    terms: list[str] = []
    if expanded_terms:
        terms.extend(term for term in expanded_terms if term)

    query_text = normalize_query_term(query)
    for marker, marker_terms in QUERY_EXPANSIONS.items():
        if contains_query_marker(query_text, marker):
            terms.extend(marker_terms)

    terms.extend(contextual_expansion_terms(query_text, terms))
    return _dedupe_terms(terms)


def contextual_expansion_terms(
    query_text: str,
    terms: Iterable[str],
) -> list[str]:
    normalized_terms = {normalize_query_term(term) for term in terms if term}
    normalized_query = normalize_query_term(query_text)
    expansions: list[str] = []

    if _has_all(normalized_terms, "fever", "cough") and _has_any(
        normalized_terms,
        "sore throat",
        "body aches",
        "muscle aches",
    ):
        expansions.extend(FLU_RESPIRATORY_COMBO_EXPANSIONS)

    has_cold_symptoms = _has_all(normalized_terms, "runny nose", "sneezing")
    has_high_risk_respiratory_sign = _has_any(
        normalized_terms,
        "high fever",
        "shortness of breath",
        "difficulty breathing",
    ) or any(
        contains_query_marker(normalized_query, marker)
        for marker in ("high fever", "shortness of breath", "difficulty breathing")
    )
    if has_cold_symptoms and not has_high_risk_respiratory_sign:
        expansions.extend(COMMON_COLD_COMBO_EXPANSIONS)

    return expansions


def _has_all(terms: set[str], *required: str) -> bool:
    return all(term in terms for term in required)


def _has_any(terms: set[str], *candidates: str) -> bool:
    return any(term in terms for term in candidates)


def contains_query_marker(text: str, marker: str) -> bool:
    normalized_text = normalize_query_term(text)
    normalized_marker = normalize_query_term(marker)
    return re.search(rf"(?<!\w){re.escape(normalized_marker)}(?!\w)", normalized_text) is not None


def normalize_query_term(text: str) -> str:
    return " ".join(text.lower().strip().split())


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"\b\w+\b", text.lower(), flags=re.UNICODE)
    return [token for token in tokens if token.isascii() and token.replace("_", "").isalnum()]


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _dedupe_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = normalize_query_term(term)
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--vector-top-k", type=int, default=30)
    parser.add_argument("--bm25-top-k", type=int, default=30)
    parser.add_argument("--expanded", nargs="*", default=None)
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    retriever = HybridRetrieverAgent()
    result = retriever.run(
        query=args.query,
        top_k=args.top_k,
        mode=args.mode,
        expanded_terms=args.expanded,
        vector_top_k=args.vector_top_k,
        bm25_top_k=args.bm25_top_k,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
