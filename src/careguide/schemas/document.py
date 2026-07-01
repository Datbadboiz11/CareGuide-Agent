from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


SourceName = Literal["NHS", "MedlinePlus", "CDC"]


class OfficialSourceConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: SourceName
    url: HttpUrl
    topic: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"] = "medium"
    symptom_group: str = Field(min_length=1)


class DocumentSection(BaseModel):

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1)
    content: str = Field(min_length=1)
    section_type: str = Field(min_length=1)


class OfficialHealthDocument(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: SourceName
    url: HttpUrl
    title: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    symptom_group: str = Field(min_length=1)
    page_last_reviewed: str | None = None
    next_review_due: str | None = None
    sections: list[DocumentSection] = Field(min_length=1)

    @field_validator("sections")
    @classmethod
    def sections_must_have_unique_headings(cls, value: list[DocumentSection]) -> list[DocumentSection]:
        headings = [section.heading for section in value]
        if len(headings) != len(set(headings)):
            raise ValueError("section headings must be unique within one document")
        return value
