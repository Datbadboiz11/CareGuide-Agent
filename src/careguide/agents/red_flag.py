from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import NormalizationResult, NormalizedSymptom
from careguide.schemas.red_flags import RedFlagFinding, RedFlagResult, RedFlagSeverity


DEFAULT_RED_FLAG_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "safety" / "red_flags.yaml"
)

EMERGENCY_MARKERS = (
    "dữ dội",
    "đột ngột",
    "ép nặng",
    "lan lên hàm",
    "không nói được",
    "phải ngồi",
    "tím",
    "lơ mơ",
    "ngất",
    "vã mồ hôi",
)


class RedFlagAgent:

    def __init__(self, rules_path: str | Path = DEFAULT_RED_FLAG_RULES_PATH) -> None:
        self.rules_path = Path(rules_path)
        self.rules = load_red_flag_rules(self.rules_path)

    def run(
        self,
        parsed: ParsedClinicalInfo,
        normalized: NormalizationResult,
    ) -> RedFlagResult:
        return detect_red_flags(parsed, normalized, self.rules)


def load_red_flag_rules(path: str | Path = DEFAULT_RED_FLAG_RULES_PATH) -> dict[str, Any]:
    """Load red-flag rules from YAML."""

    rules_path = Path(path)
    with rules_path.open("r", encoding="utf-8") as file:
        rules = yaml.safe_load(file)
    if not isinstance(rules, dict):
        raise ValueError(f"{rules_path}: expected a YAML mapping")
    return rules


def detect_red_flags(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
    rules: dict[str, Any] | None = None,
) -> RedFlagResult:

    rule_set = rules or load_red_flag_rules()
    findings: list[RedFlagFinding] = []

    for symptom in normalized.normalized_symptoms:
        if symptom.negated:
            continue
        finding = _finding_from_symptom(symptom, parsed, rule_set)
        if finding is not None:
            findings.append(finding)

    findings.extend(_vital_findings(parsed, rule_set))
    findings.extend(_combination_findings(parsed, normalized))
    findings.extend(_risk_factor_findings(parsed, normalized))

    deduped = _dedupe_findings(findings)
    highest = _highest_severity(deduped)
    return RedFlagResult(
        red_flags=deduped,
        highest_severity=highest,
        requires_urgent=highest in {"urgent", "emergency"},
        requires_emergency=highest == "emergency",
    )


def _finding_from_symptom(
    symptom: NormalizedSymptom,
    parsed: ParsedClinicalInfo,
    rules: dict[str, Any],
) -> RedFlagFinding | None:
    canonical_rules = rules.get("canonical_rules", {})
    rule = canonical_rules.get(symptom.canonical)
    if not rule:
        return None

    severity = _adjust_symptom_severity(symptom, parsed, rule["severity"])
    return RedFlagFinding(
        name=rule["name"],
        severity=severity,
        source="symptom",
        evidence=symptom.original,
        canonical=symptom.canonical,
        reason=rule["reason"],
    )


def _adjust_symptom_severity(
    symptom: NormalizedSymptom,
    parsed: ParsedClinicalInfo,
    default_severity: RedFlagSeverity,
) -> RedFlagSeverity:
    raw = parsed.raw_text.lower()
    original = symptom.original.lower()

    if symptom.canonical == "chest pain":
        if any(marker in original for marker in EMERGENCY_MARKERS):
            return "emergency"
        if _has_canonical(parsed=None, normalized_text=raw, candidates=("shortness of breath",)):
            return "emergency"
        return "urgent"

    if symptom.canonical == "shortness of breath":
        if any(marker in original for marker in EMERGENCY_MARKERS):
            return "emergency"
        if _spo2(parsed) is not None and _spo2(parsed) <= 90:
            return "emergency"
        return "urgent"

    if symptom.canonical == "photophobia" and ("sốt" in raw or "đau đầu" in raw):
        return "urgent"

    return default_severity


def _vital_findings(parsed: ParsedClinicalInfo, rules: dict[str, Any]) -> list[RedFlagFinding]:
    vital_rules = rules.get("vital_rules", {})
    findings: list[RedFlagFinding] = []

    spo2 = _spo2(parsed)
    if spo2 is not None:
        if spo2 <= vital_rules["spo2_emergency_max"]:
            findings.append(
                _vital_finding("Low SpO2", "emergency", f"SpO2 {spo2}%", "Low oxygen saturation")
            )
        elif spo2 <= vital_rules["spo2_urgent_max"]:
            findings.append(
                _vital_finding("Low SpO2", "urgent", f"SpO2 {spo2}%", "Borderline low oxygen saturation")
            )

    temperature = parsed.vitals.get("temperature")
    if isinstance(temperature, (int, float)):
        if temperature >= vital_rules["temperature_emergency_min"]:
            findings.append(
                _vital_finding("Very high fever", "emergency", f"{temperature}°C", "Very high fever")
            )
        elif temperature >= vital_rules["temperature_urgent_min"]:
            findings.append(
                _vital_finding("High fever", "urgent", f"{temperature}°C", "High or persistent fever")
            )

    systolic, diastolic = _blood_pressure(parsed)
    if systolic is not None and diastolic is not None:
        if (
            systolic >= vital_rules["systolic_bp_emergency_min"]
            or diastolic >= vital_rules["diastolic_bp_emergency_min"]
        ):
            findings.append(
                _vital_finding(
                    "Severely high blood pressure",
                    "emergency",
                    f"{systolic}/{diastolic}",
                    "Severely high blood pressure",
                )
            )
        elif (
            systolic >= vital_rules["systolic_bp_urgent_min"]
            or diastolic >= vital_rules["diastolic_bp_urgent_min"]
        ):
            findings.append(
                _vital_finding(
                    "High blood pressure",
                    "urgent",
                    f"{systolic}/{diastolic}",
                    "High blood pressure with symptoms",
                )
            )

    return findings


def _combination_findings(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
) -> list[RedFlagFinding]:
    canonical = _positive_canonicals(normalized)
    raw = parsed.raw_text.lower()
    findings: list[RedFlagFinding] = []

    if "chest pain" in canonical and "shortness of breath" in canonical:
        findings.append(
            RedFlagFinding(
                name="Chest pain with shortness of breath",
                severity="emergency",
                source="combination",
                evidence="chest pain + shortness of breath",
                canonical="chest pain",
                reason="Chest pain with breathing difficulty can indicate a serious condition.",
            )
        )

    if "fever" in canonical and (
        "neck stiffness" in canonical
        or "altered mental status" in canonical
        or "seizure" in canonical
        or "phát ban" in raw
    ):
        findings.append(
            RedFlagFinding(
                name="Fever with neurologic or rash red flags",
                severity="emergency",
                source="combination",
                evidence="fever with neurologic/rash signs",
                canonical="fever",
                reason="Fever with neck stiffness, confusion, seizure or purpuric rash can be dangerous.",
            )
        )

    if {"hives", "lip swelling", "facial swelling"} & canonical and "shortness of breath" in canonical:
        findings.append(
            RedFlagFinding(
                name="Possible severe allergic reaction",
                severity="emergency",
                source="combination",
                evidence="allergy signs + shortness of breath",
                canonical="shortness of breath",
                reason="Swelling or hives with breathing symptoms can indicate anaphylaxis.",
            )
        )

    if "missed period" in canonical and (
        "abdominal pain" in canonical or "dizziness" in canonical or "syncope" in canonical
    ):
        findings.append(
            RedFlagFinding(
                name="Possible pregnancy-related emergency",
                severity="emergency",
                source="combination",
                evidence="missed period with severe abdominal pain or faintness",
                canonical="missed period",
                reason="Missed period with severe abdominal pain or faintness needs urgent assessment.",
            )
        )

    if "head injury" in canonical and (
        "vomiting" in canonical or "altered mental status" in canonical or "headache" in canonical
    ):
        findings.append(
            RedFlagFinding(
                name="Head injury with warning signs",
                severity="emergency",
                source="combination",
                evidence="head injury with vomiting/headache/drowsiness",
                canonical="head injury",
                reason="Head injury with vomiting, headache or abnormal drowsiness needs emergency assessment.",
            )
        )

    if "leg swelling" in canonical and "shortness of breath" in canonical and "chest pain" in canonical:
        findings.append(
            RedFlagFinding(
                name="Chest pain and shortness of breath after immobility",
                severity="emergency",
                source="combination",
                evidence="chest pain + shortness of breath + swollen leg",
                canonical="chest pain",
                reason="This combination can indicate a serious clot-related condition.",
            )
        )

    if _has_carbon_monoxide_risk(raw, canonical):
        findings.append(
            RedFlagFinding(
                name="Possible carbon monoxide poisoning",
                severity="emergency",
                source="combination",
                evidence="gas exposure in enclosed space with compatible symptoms",
                canonical="carbon monoxide poisoning",
                reason="Symptoms after possible gas exposure in an enclosed space can indicate carbon monoxide poisoning.",
            )
        )

    if _has_dengue_warning_risk(parsed, raw, canonical):
        findings.append(
            RedFlagFinding(
                name="Possible dengue warning signs",
                severity="urgent",
                source="combination",
                evidence="fever after tropical travel with bleeding symptoms",
                canonical="dengue",
                reason="Fever after travel to a dengue-risk area with bleeding symptoms needs prompt medical assessment.",
            )
        )

    return findings


def _risk_factor_findings(
    parsed: ParsedClinicalInfo,
    normalized: NormalizationResult,
) -> list[RedFlagFinding]:
    canonical = _positive_canonicals(normalized)
    findings: list[RedFlagFinding] = []

    if "thai kỳ" in parsed.risk_factors and (
        "fever" in canonical or "abdominal pain" in canonical or "vaginal bleeding" in canonical
    ):
        severity: RedFlagSeverity = "emergency" if "vaginal bleeding" in canonical else "urgent"
        findings.append(
            RedFlagFinding(
                name="Pregnancy risk factor",
                severity=severity,
                source="risk_factor",
                evidence="thai kỳ",
                canonical=None,
                reason="Fever, abdominal pain or bleeding during pregnancy needs medical assessment.",
            )
        )

    if "trẻ nhỏ" in parsed.risk_factors and ("fever" in canonical or "seizure" in canonical):
        severity = "emergency" if "seizure" in canonical or "cyanosis" in canonical else "urgent"
        findings.append(
            RedFlagFinding(
                name="Young child risk factor",
                severity=severity,
                source="risk_factor",
                evidence="trẻ nhỏ",
                canonical=None,
                reason="Fever or neurologic symptoms in a young child need careful assessment.",
            )
        )

    if "người già" in parsed.risk_factors and (
        "fever" in canonical
        or "shortness of breath" in canonical
        or "abdominal pain" in canonical
        or "dizziness" in canonical
    ):
        findings.append(
            RedFlagFinding(
                name="Older adult risk factor",
                severity="urgent",
                source="risk_factor",
                evidence="người già",
                canonical=None,
                reason="Older adults have higher risk of complications from these symptoms.",
            )
        )

    if "đái tháo đường" in parsed.risk_factors and (
        "fever" in canonical or "wound redness" in canonical or "localized swelling" in canonical
    ):
        findings.append(
            RedFlagFinding(
                name="Diabetes risk factor",
                severity="urgent",
                source="risk_factor",
                evidence="đái tháo đường",
                canonical=None,
                reason="Diabetes increases risk from infection or wounds.",
            )
        )

    if "bệnh hen" in parsed.risk_factors and "shortness of breath" in canonical:
        findings.append(
            RedFlagFinding(
                name="Asthma with breathing symptoms",
                severity="urgent",
                source="risk_factor",
                evidence="bệnh hen",
                canonical="shortness of breath",
                reason="Asthma symptoms can worsen quickly.",
            )
        )

    if "thuốc chống đông" in parsed.risk_factors and "bruising" in canonical:
        findings.append(
            RedFlagFinding(
                name="Anticoagulant bleeding risk",
                severity="urgent",
                source="risk_factor",
                evidence="thuốc chống đông",
                canonical="bruising",
                reason="Anticoagulants increase bleeding risk after bruising or injury.",
            )
        )

    return findings


def _positive_canonicals(normalized: NormalizationResult) -> set[str]:
    return {item.canonical for item in normalized.normalized_symptoms if not item.negated}


def _has_carbon_monoxide_risk(raw: str, canonical: set[str]) -> bool:
    has_enclosed_space = any(marker in raw for marker in ("phòng kín", "phong kin", "kín", "kin"))
    has_gas_source = any(marker in raw for marker in ("bếp gas", "bep gas", "khí gas", "khi gas", "gas"))
    has_compatible_symptom = bool(
        canonical
        & {
            "headache",
            "dizziness",
            "nausea",
            "vomiting",
            "altered mental status",
            "syncope",
        }
    ) or any(
        marker in raw
        for marker in (
            "đau đầu",
            "dau dau",
            "chóng mặt",
            "chong mat",
            "buồn nôn",
            "buon non",
            "lơ mơ",
            "lo mo",
            "lú lẫn",
            "lu lan",
            "ngất",
            "ngat",
        )
    )
    return has_enclosed_space and has_gas_source and has_compatible_symptom


def _has_dengue_warning_risk(
    parsed: ParsedClinicalInfo,
    raw: str,
    canonical: set[str],
) -> bool:
    temperature = parsed.vitals.get("temperature")
    has_fever = "fever" in canonical or "sốt" in raw or (
        isinstance(temperature, (int, float)) and temperature >= 38.5
    )
    has_travel_or_exposure = any(
        marker in raw
        for marker in (
            "vùng nhiệt đới",
            "vung nhiet doi",
            "nhiệt đới",
            "nhiet doi",
            "đi vùng",
            "di vung",
            "dengue",
        )
    )
    has_bleeding = any(
        marker in raw
        for marker in (
            "chảy máu",
            "chay mau",
            "chảy máu chân răng",
            "chay mau chan rang",
            "xuất huyết",
            "xuat huyet",
        )
    )
    return has_fever and has_travel_or_exposure and has_bleeding


def _spo2(parsed: ParsedClinicalInfo) -> int | None:
    spo2 = parsed.vitals.get("spo2")
    return spo2 if isinstance(spo2, int) else None


def _blood_pressure(parsed: ParsedClinicalInfo) -> tuple[int | None, int | None]:
    bp = parsed.vitals.get("blood_pressure")
    if not isinstance(bp, str) or "/" not in bp:
        return None, None
    systolic, diastolic = bp.split("/", maxsplit=1)
    return int(systolic), int(diastolic)


def _vital_finding(
    name: str,
    severity: RedFlagSeverity,
    evidence: str,
    reason: str,
) -> RedFlagFinding:
    return RedFlagFinding(
        name=name,
        severity=severity,
        source="vital",
        evidence=evidence,
        canonical=None,
        reason=reason,
    )


def _dedupe_findings(findings: list[RedFlagFinding]) -> list[RedFlagFinding]:
    severity_rank = {"urgent": 1, "emergency": 2}
    by_name: dict[str, RedFlagFinding] = {}
    for finding in findings:
        existing = by_name.get(finding.name)
        if existing is None or severity_rank[finding.severity] > severity_rank[existing.severity]:
            by_name[finding.name] = finding
    return sorted(
        by_name.values(),
        key=lambda item: (severity_rank[item.severity], item.name),
        reverse=True,
    )


def _highest_severity(findings: list[RedFlagFinding]) -> RedFlagSeverity | None:
    if any(finding.severity == "emergency" for finding in findings):
        return "emergency"
    if any(finding.severity == "urgent" for finding in findings):
        return "urgent"
    return None


def _has_canonical(
    parsed: ParsedClinicalInfo | None,
    normalized_text: str,
    candidates: tuple[str, ...],
) -> bool:
    if "shortness of breath" in candidates:
        return "khó thở" in normalized_text
    return False
