from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TriageLabel = Literal["self_care", "routine_visit", "urgent_visit", "emergency"]
Difficulty = Literal["simple", "medium", "complex"]


class TriageTestCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    difficulty: Difficulty
    category: TriageLabel
    user_input: str = Field(min_length=1)
    expected_triage: TriageLabel
    expected_symptoms: list[str]
    expected_negated_symptoms: list[str] = Field(default_factory=list)
    expected_vitals: dict[str, Any] = Field(default_factory=dict)
    expected_red_flags: list[str] = Field(default_factory=list)
    expected_missing_info: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator(
        "expected_symptoms",
        "expected_negated_symptoms",
        "expected_red_flags",
        "expected_missing_info",
        "risk_factors",
    )
    @classmethod
    def no_blank_list_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("list fields must not contain blank strings")
        return value

    @field_validator("category")
    @classmethod
    def category_matches_expected_triage(cls, value: TriageLabel, info: Any) -> TriageLabel:
        expected = info.data.get("expected_triage")
        if expected is not None and value != expected:
            raise ValueError("category must match expected_triage")
        return value


class SafetyTestCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    case_type: str = Field(min_length=1)
    triage_level: TriageLabel
    candidate_response: str = Field(min_length=1)
    expected_safety_pass: bool
    expected_violations: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("expected_violations")
    @classmethod
    def no_blank_violations(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("expected_violations must not contain blank strings")
        return value

    @field_validator("expected_violations")
    @classmethod
    def passing_cases_have_no_violations(cls, value: list[str], info: Any) -> list[str]:
        expected_safety_pass = info.data.get("expected_safety_pass")
        if expected_safety_pass is True and value:
            raise ValueError("safe cases must not list expected violations")
        if expected_safety_pass is False and not value:
            raise ValueError("unsafe cases must list at least one expected violation")
        return value
