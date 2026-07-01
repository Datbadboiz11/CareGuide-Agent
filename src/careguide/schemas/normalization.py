"""Schemas for symptom normalization."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SymptomVocabularyEntry(BaseModel):
    """One canonical medical concept with Vietnamese aliases."""

    model_config = ConfigDict(extra="forbid")

    canonical: str = Field(min_length=1)
    category: str = Field(min_length=1)
    aliases_vi: list[str] = Field(min_length=1)
    severity_hint: str | None = None
    red_flag_hint: bool = False


class NormalizedSymptom(BaseModel):
    """A normalized symptom mention."""

    model_config = ConfigDict(extra="forbid")

    original: str
    canonical: str
    category: str
    negated: bool = False
    confidence: float
    matched_alias: str
    red_flag_hint: bool = False


class NormalizationResult(BaseModel):
    """Normalizer output for one parsed clinical input."""

    model_config = ConfigDict(extra="forbid")

    normalized_symptoms: list[NormalizedSymptom] = Field(default_factory=list)
    unmatched_terms: list[str] = Field(default_factory=list)
