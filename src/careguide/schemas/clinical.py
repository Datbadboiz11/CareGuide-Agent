from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParsedClinicalInfo(BaseModel):

    model_config = ConfigDict(extra="forbid")

    symptoms: list[str] = Field(default_factory=list)
    negated_symptoms: list[str] = Field(default_factory=list)
    duration: str | None = None
    severity: list[str] = Field(default_factory=list)
    vitals: dict[str, Any] = Field(default_factory=dict)
    risk_factors: list[str] = Field(default_factory=list)
    raw_text: str
