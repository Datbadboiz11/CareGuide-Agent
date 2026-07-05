from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

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
SECTION_BONUS = {
    "immediate_action": 0.004,
    "urgent_advice": 0.004,
    "when_to_get_help": 0.003,
    "emergency": 0.003,
    "symptoms": 0.002,
    "overview": 0.001,
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
    ) -> RetrievalResult:
        expanded_query = build_expanded_query(query, expanded_terms)
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
            hits = weighted_rrf_fusion(
                metadata=self.metadata,
                vector_items=vector_items,
                bm25_items=bm25_items,
                top_k=top_k,
                vector_weight=self.vector_weight,
                bm25_weight=self.bm25_weight,
                rrf_k=self.rrf_k,
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
        bonus = section_bonus(item_metadata.get("section_type", ""))
        score = 0.0
        if candidate.get("vector_rank") is not None:
            score += vector_weight * reciprocal_rank(candidate["vector_rank"], rrf_k)
        if candidate.get("bm25_rank") is not None:
            score += bm25_weight * reciprocal_rank(candidate["bm25_rank"], rrf_k)
        score += bonus
        candidate["final_score"] = score
        candidate["section_bonus"] = bonus
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
    )


def reciprocal_rank(rank: int, rrf_k: int = RRF_K) -> float:
    if rank < 1:
        raise ValueError("rank must start from 1")
    return 1.0 / (rrf_k + rank)


def section_bonus(section_type: str) -> float:
    return SECTION_BONUS.get(section_type, 0.0)


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


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"\b\w+\b", text.lower(), flags=re.UNICODE)
    return [token for token in tokens if token.isascii() and token.replace("_", "").isalnum()]


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


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
