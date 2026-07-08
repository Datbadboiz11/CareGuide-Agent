from __future__ import annotations

from typing import Any, TypedDict

from careguide.schemas.answer import CareGuideAnswer
from careguide.schemas.clinical import ParsedClinicalInfo
from careguide.schemas.normalization import NormalizationResult
from careguide.schemas.red_flags import RedFlagResult
from careguide.schemas.retrieval import RetrievalHit, RetrievalResult
from careguide.schemas.triage import TriageResult


class CareGuideState(TypedDict, total=False):
    raw_input: str
    parsed: ParsedClinicalInfo
    normalized: NormalizationResult
    red_flags: RedFlagResult
    triage: TriageResult
    retrieval_query: str
    expanded_terms: list[str]
    retrieval: RetrievalResult
    answer_context: list[RetrievalHit]
    answer: CareGuideAnswer
    safety: dict[str, Any]
    final_output: dict[str, Any]
    errors: list[str]
