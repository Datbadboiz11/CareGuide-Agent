from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TriageLevel = Literal["self_care", "routine_visit", "urgent_visit", "emergency"]
TriageConfidence = Literal["low", "medium", "high"]


class TriageResult(BaseModel):

    model_config = ConfigDict(extra="forbid")

    triage_level: TriageLevel
    confidence: TriageConfidence
    main_reasons: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    recommended_action: str
    requires_urgent: bool = False
    requires_emergency: bool = False

