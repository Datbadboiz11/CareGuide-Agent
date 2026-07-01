from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


QuestionPriority = Literal["low", "medium", "high"]


class FollowUpQuestion(BaseModel):

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    priority: QuestionPriority
    topic: str = Field(min_length=1)


class QuestioningResult(BaseModel):

    model_config = ConfigDict(extra="forbid")

    should_ask: bool
    questions: list[FollowUpQuestion] = Field(default_factory=list)
    skipped_reason: str | None = None

