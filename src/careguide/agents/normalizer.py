from __future__ import annotations

import json
import re
from pathlib import Path

from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import (
    NormalizationResult,
    NormalizedSymptom,
    SymptomVocabularyEntry,
)


DEFAULT_VOCAB_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "processed" / "symptom_vocabulary.json"
)


class MedicalTermNormalizerAgent:
    """Normalize Vietnamese symptom mentions to English canonical terms."""

    def __init__(self, vocabulary_path: str | Path = DEFAULT_VOCAB_PATH) -> None:
        self.vocabulary_path = Path(vocabulary_path)
        self.vocabulary = load_symptom_vocabulary(self.vocabulary_path)
        self._alias_index = _build_alias_index(self.vocabulary)

    def run(self, parsed: ParsedClinicalInfo) -> NormalizationResult:
        return normalize_clinical_info(parsed, self.vocabulary)


def load_symptom_vocabulary(path: str | Path = DEFAULT_VOCAB_PATH) -> list[SymptomVocabularyEntry]:
    """Load symptom vocabulary JSON."""

    vocab_path = Path(path)
    with vocab_path.open("r", encoding="utf-8") as file:
        raw_entries = json.load(file)
    if not isinstance(raw_entries, list):
        raise ValueError(f"{vocab_path}: expected a JSON array")
    return [SymptomVocabularyEntry.model_validate(entry) for entry in raw_entries]


def normalize_clinical_info(
    parsed: ParsedClinicalInfo,
    vocabulary: list[SymptomVocabularyEntry] | None = None,
) -> NormalizationResult:
    """Normalize positive and negated symptoms from parsed clinical info."""

    vocab = vocabulary or load_symptom_vocabulary()
    normalized: list[NormalizedSymptom] = []
    unmatched: list[str] = []
    seen: set[tuple[str, bool]] = set()

    for term in parsed.symptoms:
        match = _match_term(term, vocab)
        if match is None:
            unmatched.append(term)
            continue
        item = _to_normalized(term, match, negated=False)
        key = (item.canonical, item.negated)
        if key not in seen:
            normalized.append(item)
            seen.add(key)

    for term in parsed.negated_symptoms:
        match = _match_term(term, vocab)
        if match is None:
            unmatched.append(term)
            continue
        item = _to_normalized(term, match, negated=True)
        key = (item.canonical, item.negated)
        if key not in seen:
            normalized.append(item)
            seen.add(key)

    return NormalizationResult(
        normalized_symptoms=normalized,
        unmatched_terms=sorted(set(unmatched)),
    )


def normalize_terms(
    symptoms: list[str],
    negated_symptoms: list[str] | None = None,
    vocabulary: list[SymptomVocabularyEntry] | None = None,
) -> NormalizationResult:

    parsed = ParsedClinicalInfo(
        symptoms=symptoms,
        negated_symptoms=negated_symptoms or [],
        raw_text="",
    )
    return normalize_clinical_info(parsed, vocabulary=vocabulary)


def _build_alias_index(
    vocabulary: list[SymptomVocabularyEntry],
) -> list[tuple[str, SymptomVocabularyEntry]]:
    aliases: list[tuple[str, SymptomVocabularyEntry]] = []
    for entry in vocabulary:
        for alias in entry.aliases_vi:
            aliases.append((_normalize_text(alias), entry))
    return sorted(aliases, key=lambda item: len(item[0]), reverse=True)


def _match_term(
    term: str,
    vocabulary: list[SymptomVocabularyEntry],
) -> tuple[SymptomVocabularyEntry, str, float] | None:
    normalized_term = _normalize_text(term)
    alias_index = _build_alias_index(vocabulary)

    for alias, entry in alias_index:
        if normalized_term == alias:
            return entry, alias, 1.0

    for alias, entry in alias_index:
        if _contains_phrase(normalized_term, alias):
            return entry, alias, 0.92

    for alias, entry in alias_index:
        if _contains_phrase(alias, normalized_term):
            return entry, alias, 0.82

    return None


def _to_normalized(
    original: str,
    match: tuple[SymptomVocabularyEntry, str, float],
    negated: bool,
) -> NormalizedSymptom:
    entry, alias, confidence = match
    return NormalizedSymptom(
        original=original,
        canonical=entry.canonical,
        category=entry.category,
        negated=negated,
        confidence=confidence,
        matched_alias=alias,
        red_flag_hint=entry.red_flag_hint,
    )


def _normalize_text(text: str) -> str:
    normalized = text.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
