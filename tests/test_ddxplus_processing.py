import json
from pathlib import Path

import pytest

from careguide.rag.process_ddxplus_sources import (
    load_conditions,
    load_evidences,
    parse_differential_diagnosis,
    parse_evidence_values,
    row_to_patient_case,
    sample_patient_cases,
)
from careguide.schemas.ddxplus import DDXPlusCondition, DDXPlusEvidence, DDXPlusPatientCase


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "ddxplus"
CONDITIONS_RAW_PATH = RAW_DIR / "release_conditions.json"
EVIDENCES_RAW_PATH = RAW_DIR / "release_evidences.json"
CONDITIONS_OUTPUT_PATH = ROOT / "data" / "processed" / "ddxplus_conditions.jsonl"
EVIDENCES_OUTPUT_PATH = ROOT / "data" / "processed" / "ddxplus_evidences.jsonl"
CASES_OUTPUT_PATH = ROOT / "data" / "processed" / "ddxplus_cases_sample.jsonl"


def test_load_ddxplus_conditions_from_raw_file() -> None:
    if not CONDITIONS_RAW_PATH.exists():
        pytest.skip("Download DDXPlus to data/raw/ddxplus first")

    conditions = load_conditions(CONDITIONS_RAW_PATH)

    assert len(conditions) == 49
    assert any(condition.condition_name_en == "Anaphylaxis" for condition in conditions)
    assert all(condition.condition_id for condition in conditions)
    assert all(condition.symptom_codes for condition in conditions)


def test_load_ddxplus_evidences_from_raw_file() -> None:
    if not EVIDENCES_RAW_PATH.exists():
        pytest.skip("Download DDXPlus to data/raw/ddxplus first")

    evidences = load_evidences(EVIDENCES_RAW_PATH)

    assert len(evidences) >= 200
    assert any(evidence.evidence_code == "E_91" for evidence in evidences)
    assert all(evidence.question_en for evidence in evidences)


def test_parse_evidence_values() -> None:
    evidences = parse_evidence_values("['E_91', 'E_55_@_V_89', 'E_56_@_4']")

    assert evidences[0].code == "E_91"
    assert evidences[0].value is None
    assert evidences[1].code == "E_55"
    assert evidences[1].value == "V_89"
    assert evidences[2].value == "4"


def test_parse_differential_diagnosis() -> None:
    differential = parse_differential_diagnosis("[['Bronchitis', 0.2], ['Pneumonia', 0.1]]")

    assert differential[0].condition_name == "Bronchitis"
    assert differential[0].probability == 0.2
    assert differential[1].condition_name == "Pneumonia"


def test_row_to_patient_case_schema() -> None:
    row = {
        "AGE": "18",
        "SEX": "M",
        "PATHOLOGY": "URTI",
        "INITIAL_EVIDENCE": "E_91",
        "EVIDENCES": "['E_91', 'E_201', 'E_204_@_V_10']",
        "DIFFERENTIAL_DIAGNOSIS": "[['URTI', 0.7], ['Influenza', 0.3]]",
    }

    case = row_to_patient_case("train", row)

    assert case.age == 18
    assert case.sex == "M"
    assert case.pathology == "URTI"
    assert case.initial_evidence == "E_91"
    assert len(case.evidences) == 3
    assert case.differential_diagnosis[0].condition_name == "URTI"


def test_sample_patient_cases_from_raw_file() -> None:
    if not RAW_DIR.exists():
        pytest.skip("Download DDXPlus to data/raw/ddxplus first")

    cases = sample_patient_cases(RAW_DIR, sample_size=5, seed=7, max_rows=50)

    assert len(cases) == 5
    assert all(case.evidences for case in cases)
    assert all(case.differential_diagnosis for case in cases)


def test_ddxplus_outputs_schema_if_files_exist() -> None:
    output_paths = [CONDITIONS_OUTPUT_PATH, EVIDENCES_OUTPUT_PATH, CASES_OUTPUT_PATH]
    if any(not path.exists() or path.stat().st_size == 0 for path in output_paths):
        pytest.skip("Run python -m careguide.rag.process_ddxplus_sources to create DDXPlus outputs")

    with CONDITIONS_OUTPUT_PATH.open("r", encoding="utf-8") as file:
        conditions = [DDXPlusCondition.model_validate(json.loads(line)) for line in file]
    with EVIDENCES_OUTPUT_PATH.open("r", encoding="utf-8") as file:
        evidences = [DDXPlusEvidence.model_validate(json.loads(line)) for line in file]
    with CASES_OUTPUT_PATH.open("r", encoding="utf-8") as file:
        cases = [DDXPlusPatientCase.model_validate(json.loads(line)) for line in file]

    assert len(conditions) == 49
    assert len(evidences) >= 200
    assert cases
