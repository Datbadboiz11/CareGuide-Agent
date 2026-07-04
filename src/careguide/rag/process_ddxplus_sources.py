from __future__ import annotations

import argparse
import ast
import csv
import json
import random
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from careguide.schemas.ddxplus import (
    DDXPlusCondition,
    DDXPlusDifferentialDiagnosisItem,
    DDXPlusEvidence,
    DDXPlusEvidenceValue,
    DDXPlusPatientCase,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "ddxplus"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed"
DEFAULT_CONDITIONS_OUTPUT = DEFAULT_OUTPUT_DIR / "ddxplus_conditions.jsonl"
DEFAULT_EVIDENCES_OUTPUT = DEFAULT_OUTPUT_DIR / "ddxplus_evidences.jsonl"
DEFAULT_CASES_OUTPUT = DEFAULT_OUTPUT_DIR / "ddxplus_cases_sample.jsonl"

SPLIT_FILES = {
    "train": Path("release_train_patients") / "release_train_patients",
    "validate": Path("release_validate_patients") / "release_validate_patients",
    "test": Path("release_test_patients") / "release_test_patients",
}


def main() -> None:
    args = _parse_args()
    raw_dir = Path(args.raw_dir)

    conditions = load_conditions(raw_dir / "release_conditions.json")
    evidences = load_evidences(raw_dir / "release_evidences.json")
    cases = sample_patient_cases(
        raw_dir=raw_dir,
        sample_size=args.sample_size,
        seed=args.seed,
        max_rows=args.max_rows,
    )

    write_jsonl(args.conditions_output, conditions)
    write_jsonl(args.evidences_output, evidences)
    write_jsonl(args.cases_output, cases)

    print(f"Wrote {len(conditions)} DDXPlus conditions to {args.conditions_output}")
    print(f"Wrote {len(evidences)} DDXPlus evidences to {args.evidences_output}")
    print(f"Wrote {len(cases)} DDXPlus sample cases to {args.cases_output}")


def load_conditions(path: str | Path) -> list[DDXPlusCondition]:
    raw = _load_json_mapping(path)
    conditions: list[DDXPlusCondition] = []

    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        name = str(value.get("condition_name") or key)
        conditions.append(
            DDXPlusCondition(
                condition_id=_slug(name),
                condition_name=name,
                condition_name_en=str(value.get("cond-name-eng") or name),
                condition_name_fr=_optional_str(value.get("cond-name-fr")),
                icd10_id=_optional_str(value.get("icd10-id")),
                severity=_optional_int(value.get("severity")),
                symptom_codes=sorted(_dict_keys(value.get("symptoms"))),
                antecedent_codes=sorted(_dict_keys(value.get("antecedents"))),
            )
        )

    return sorted(conditions, key=lambda item: item.condition_name_en.lower())


def load_evidences(path: str | Path) -> list[DDXPlusEvidence]:
    raw = _load_json_mapping(path)
    evidences: list[DDXPlusEvidence] = []

    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        question_en = _clean_text(str(value.get("question_en") or key))
        evidences.append(
            DDXPlusEvidence(
                evidence_code=str(value.get("name") or key),
                question_en=question_en,
                question_fr=_optional_str(value.get("question_fr")),
                is_antecedent=bool(value.get("is_antecedent")),
                data_type=str(value.get("data_type") or "unknown"),
                default_value=value.get("default_value"),
                possible_values=[str(item) for item in value.get("possible-values", [])],
                value_meaning=_normalize_value_meaning(value.get("value_meaning")),
            )
        )

    return sorted(evidences, key=lambda item: item.evidence_code)


def sample_patient_cases(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    sample_size: int = 10000,
    seed: int = 42,
    max_rows: int | None = None,
) -> list[DDXPlusPatientCase]:
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")

    rng = random.Random(seed)
    reservoir: list[DDXPlusPatientCase] = []
    seen = 0

    for split, row in iter_patient_rows(raw_dir):
        seen += 1
        if max_rows is not None and seen > max_rows:
            break

        if len(reservoir) < sample_size:
            reservoir.append(row_to_patient_case(split, row))
            continue

        index = rng.randint(0, seen - 1)
        if index < sample_size:
            reservoir[index] = row_to_patient_case(split, row)

    return reservoir


def iter_patient_rows(raw_dir: str | Path = DEFAULT_RAW_DIR) -> Iterator[tuple[str, dict[str, str]]]:
    root = Path(raw_dir)
    for split, relative_path in SPLIT_FILES.items():
        path = root / relative_path
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                yield split, row


def row_to_patient_case(split: str, row: dict[str, str]) -> DDXPlusPatientCase:
    return DDXPlusPatientCase(
        split=split,
        age=int(row["AGE"]),
        sex=row["SEX"],
        pathology=row["PATHOLOGY"],
        initial_evidence=_evidence_code(row["INITIAL_EVIDENCE"]),
        evidences=parse_evidence_values(row["EVIDENCES"]),
        differential_diagnosis=parse_differential_diagnosis(row["DIFFERENTIAL_DIAGNOSIS"]),
    )


def parse_evidence_values(raw: str) -> list[DDXPlusEvidenceValue]:
    values = ast.literal_eval(raw)
    if not isinstance(values, list):
        raise ValueError("EVIDENCES must be a list")

    result: list[DDXPlusEvidenceValue] = []
    for item in values:
        item_text = str(item)
        code, value = _split_evidence_value(item_text)
        result.append(DDXPlusEvidenceValue(code=code, value=value, raw=item_text))
    return result


def parse_differential_diagnosis(raw: str) -> list[DDXPlusDifferentialDiagnosisItem]:
    values = ast.literal_eval(raw)
    if not isinstance(values, list):
        raise ValueError("DIFFERENTIAL_DIAGNOSIS must be a list")

    result: list[DDXPlusDifferentialDiagnosisItem] = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        result.append(
            DDXPlusDifferentialDiagnosisItem(
                condition_name=str(item[0]),
                probability=float(item[1]),
            )
        )
    return result


def write_jsonl(path: str | Path, records: Iterable[Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            if hasattr(record, "model_dump"):
                payload = record.model_dump(mode="json")
            else:
                payload = record
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json_mapping(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected JSON object")
    return raw


def _split_evidence_value(raw: str) -> tuple[str, str | None]:
    if "_@_" not in raw:
        return raw, None
    code, value = raw.split("_@_", 1)
    return code, value


def _evidence_code(raw: str) -> str:
    return _split_evidence_value(raw)[0]


def _dict_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [str(key) for key in value.keys()]


def _normalize_value_meaning(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, dict[str, str]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        result[str(key)] = {str(inner_key): str(inner_value) for inner_key, inner_value in item.items()}
    return result


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    value = value.strip("_").lower()
    return value or "ddxplus"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--conditions-output", type=Path, default=DEFAULT_CONDITIONS_OUTPUT)
    parser.add_argument("--evidences-output", type=Path, default=DEFAULT_EVIDENCES_OUTPUT)
    parser.add_argument("--cases-output", type=Path, default=DEFAULT_CASES_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
