from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DDXPlusCondition(BaseModel):

    model_config = ConfigDict(extra="forbid")

    condition_id: str = Field(min_length=1)
    condition_name: str = Field(min_length=1)
    condition_name_en: str = Field(min_length=1)
    condition_name_fr: str | None = None
    icd10_id: str | None = None
    severity: int | None = None
    symptom_codes: list[str] = Field(default_factory=list)
    antecedent_codes: list[str] = Field(default_factory=list)


class DDXPlusEvidence(BaseModel):

    model_config = ConfigDict(extra="forbid")

    evidence_code: str = Field(min_length=1)
    question_en: str = Field(min_length=1)
    question_fr: str | None = None
    is_antecedent: bool
    data_type: str = Field(min_length=1)
    default_value: Any = None
    possible_values: list[str] = Field(default_factory=list)
    value_meaning: dict[str, dict[str, str]] = Field(default_factory=dict)


class DDXPlusEvidenceValue(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    value: str | None = None
    raw: str = Field(min_length=1)


class DDXPlusDifferentialDiagnosisItem(BaseModel):

    model_config = ConfigDict(extra="forbid")

    condition_name: str = Field(min_length=1)
    probability: float = Field(ge=0)


class DDXPlusPatientCase(BaseModel):

    model_config = ConfigDict(extra="forbid")

    split: Literal["train", "validate", "test"]
    age: int = Field(ge=0)
    sex: Literal["M", "F"]
    pathology: str = Field(min_length=1)
    initial_evidence: str = Field(min_length=1)
    evidences: list[DDXPlusEvidenceValue] = Field(min_length=1)
    differential_diagnosis: list[DDXPlusDifferentialDiagnosisItem] = Field(min_length=1)
