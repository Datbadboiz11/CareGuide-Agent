from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


RetrievalMode = Literal["vector", "bm25", "hybrid"]


class RetrievalHit(BaseModel):

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source: Literal["NHS", "MedlinePlus", "CDC"]
    url: HttpUrl
    title: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    section_heading: str = Field(min_length=1)
    section_type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    final_score: float
    vector_rank: int | None = None
    bm25_rank: int | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    section_bonus: float = 0.0


class RetrievalResult(BaseModel):

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    expanded_query: str | None = None
    mode: RetrievalMode
    top_k: int = Field(ge=1)
    vector_top_k: int = Field(ge=0)
    bm25_top_k: int = Field(ge=0)
    results: list[RetrievalHit] = Field(default_factory=list)
