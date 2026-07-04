from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Iterator

from careguide.schemas.document import OfficialHealthDocument
from careguide.schemas.rag import RagChunk


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_PATH = ROOT / "data" / "processed" / "official_rag_corpus.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "processed" / "official_rag_chunks.jsonl"


def main() -> None:
    args = _parse_args()
    chunks = list(
        chunk_corpus(
            input_path=args.input,
            max_words=args.max_words,
            overlap_words=args.overlap_words,
        )
    )
    write_jsonl(args.output, chunks)
    print(f"Wrote {len(chunks)} official RAG chunks to {args.output}")


def chunk_corpus(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    max_words: int = 450,
    overlap_words: int = 80,
) -> Iterator[RagChunk]:
    if max_words < 50:
        raise ValueError("max_words must be at least 50")
    if overlap_words < 0:
        raise ValueError("overlap_words must be non-negative")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words")

    for document in read_documents_jsonl(input_path):
        yield from chunk_document(document, max_words=max_words, overlap_words=overlap_words)


def chunk_document(
    document: OfficialHealthDocument,
    max_words: int = 450,
    overlap_words: int = 80,
) -> list[RagChunk]:
    chunks: list[RagChunk] = []

    for section_index, section in enumerate(document.sections):
        section_text = build_section_text(section.heading, section.content)
        text_chunks = split_text_by_words(section_text, max_words=max_words, overlap_words=overlap_words)

        for chunk_index, text in enumerate(text_chunks):
            chunk_id = build_chunk_id(document.id, section_index, chunk_index)
            chunks.append(
                RagChunk(
                    chunk_id=chunk_id,
                    document_id=document.id,
                    source=document.source,
                    url=document.url,
                    title=document.title,
                    topic=document.topic,
                    priority=document.priority,
                    symptom_group=document.symptom_group,
                    section_index=section_index,
                    section_heading=section.heading,
                    section_type=section.section_type,
                    chunk_index=chunk_index,
                    text=text,
                    word_count=count_words(text),
                )
            )

    return chunks


def split_text_by_words(
    text: str,
    max_words: int = 450,
    overlap_words: int = 80,
) -> list[str]:
    words = tokenize_words(text)
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    step = max_words - overlap_words

    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += step

    return chunks


def read_documents_jsonl(path: str | Path) -> Iterator[OfficialHealthDocument]:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing official RAG corpus: {input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield OfficialHealthDocument.model_validate(json.loads(stripped))
            except Exception as exc:
                raise ValueError(f"{input_path}:{line_number}: invalid OfficialHealthDocument") from exc


def build_section_text(heading: str, content: str) -> str:
    return clean_text(f"{heading}\n{content}")


def tokenize_words(text: str) -> list[str]:
    return clean_text(text).split()


def count_words(text: str) -> int:
    return len(tokenize_words(text))


def build_chunk_id(document_id: str, section_index: int, chunk_index: int) -> str:
    return f"{document_id}__section_{section_index}__chunk_{chunk_index}"


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def write_jsonl(path: str | Path, chunks: Iterable[RagChunk]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-words", type=int, default=450)
    parser.add_argument("--overlap-words", type=int, default=80)
    return parser.parse_args()


if __name__ == "__main__":
    main()
