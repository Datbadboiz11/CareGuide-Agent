from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from careguide.schemas.triage import TriageLevel


class AnswerCitation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source: Literal["NHS", "MedlinePlus", "CDC"]
    title: str = Field(min_length=1)
    url: HttpUrl
    chunk_id: str = Field(min_length=1)
    section_heading: str = Field(min_length=1)
    section_type: str = Field(min_length=1)


class CareGuideAnswer(BaseModel):

    model_config = ConfigDict(extra="forbid")

    triage_level: TriageLevel
    confidence: str = Field(min_length=1)
    user_summary: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    care_advice: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    when_to_seek_help: str = Field(min_length=1)
    related_health_topics: list[str] = Field(default_factory=list)
    citations: list[AnswerCitation] = Field(default_factory=list)
    safety_disclaimer: str = Field(min_length=1)
