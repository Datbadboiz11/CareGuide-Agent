from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RagChunk(BaseModel):

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source: Literal["NHS", "MedlinePlus", "CDC"]
    url: HttpUrl
    title: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    symptom_group: str = Field(min_length=1)
    section_index: int = Field(ge=0)
    section_heading: str = Field(min_length=1)
    section_type: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    word_count: int = Field(ge=1)
