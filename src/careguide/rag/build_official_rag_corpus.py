from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from careguide.schemas.document import OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUTS = (
    ROOT / "data" / "processed" / "official_health_documents.jsonl",
    ROOT / "data" / "processed" / "cdc_documents.jsonl",
    ROOT / "data" / "processed" / "medlineplus_documents.jsonl",
)
DEFAULT_OUTPUT_PATH = ROOT / "data" / "processed" / "official_rag_corpus.jsonl"


def main() -> None:
    args = _parse_args()
    documents = build_official_corpus(args.inputs)
    write_jsonl(args.output, documents)
    source_counts = count_by_source(documents)

    print(f"Wrote {len(documents)} official RAG documents to {args.output}")
    for source, count in sorted(source_counts.items()):
        print(f"{source}: {count}")


def build_official_corpus(paths: Iterable[str | Path]) -> list[OfficialHealthDocument]:
    documents: list[OfficialHealthDocument] = []
    seen: set[str] = set()

    for path in paths:
        for document in read_documents_jsonl(path):
            key = f"{document.source}:{document.id}"
            if key in seen:
                continue
            seen.add(key)
            documents.append(document)

    return documents


def read_documents_jsonl(path: str | Path) -> list[OfficialHealthDocument]:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing processed document file: {input_path}")

    documents: list[OfficialHealthDocument] = []
    with input_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                documents.append(OfficialHealthDocument.model_validate(json.loads(stripped)))
            except Exception as exc:
                raise ValueError(f"{input_path}:{line_number}: invalid OfficialHealthDocument") from exc

    return documents


def count_by_source(documents: Iterable[OfficialHealthDocument]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for document in documents:
        counts[document.source] = counts.get(document.source, 0) + 1
    return counts


def write_jsonl(path: str | Path, documents: Iterable[OfficialHealthDocument]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", type=Path, default=list(DEFAULT_INPUTS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    main()
