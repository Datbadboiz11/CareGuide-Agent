from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RedFlagSeverity = Literal["urgent", "emergency"]


class RedFlagFinding(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    severity: RedFlagSeverity
    source: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    canonical: str | None = None
    reason: str = Field(min_length=1)


class RedFlagResult(BaseModel):

    model_config = ConfigDict(extra="forbid")

    red_flags: list[RedFlagFinding] = Field(default_factory=list)
    highest_severity: RedFlagSeverity | None = None
    requires_urgent: bool = False
    requires_emergency: bool = False

