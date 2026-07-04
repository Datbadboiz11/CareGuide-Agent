from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from careguide.schemas.document import DocumentSection, OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_PATH = ROOT / "data" / "raw" / "medlineplus" / "mplus_topics_2026-06-27.xml"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "processed" / "medlineplus_documents.jsonl"

GROUP_TO_SYMPTOM_GROUP = {
    "blood, heart and circulation": "cardiovascular",
    "bones, joints and muscles": "musculoskeletal",
    "brain and nerves": "neurologic",
    "cancers": "oncology",
    "children and teenagers": "pediatric",
    "diabetes mellitus": "endocrine",
    "diagnostic tests": "diagnostic_tests",
    "digestive system": "gastrointestinal",
    "ear, nose and throat": "ent",
    "endocrine system": "endocrine",
    "eyes and vision": "ophthalmology",
    "female reproductive system": "reproductive",
    "immune system": "immune",
    "infections": "infectious_disease",
    "injuries and wounds": "injury",
    "kidneys and urinary system": "renal_urinary",
    "lungs and breathing": "respiratory",
    "male reproductive system": "reproductive",
    "mental health and behavior": "mental_health",
    "metabolic problems": "metabolic",
    "mouth and teeth": "dental",
    "nutrition": "nutrition",
    "pregnancy and reproduction": "pregnancy",
    "skin, hair and nails": "skin",
    "symptoms": "symptoms",
    "women's health": "women_health",
}


def main() -> None:
    args = _parse_args()
    documents = parse_medlineplus_xml(
        input_path=args.input,
        english_only=not args.include_non_english,
        max_documents=args.max_documents,
    )
    write_jsonl(args.output, documents)
    print(f"Wrote {len(documents)} MedlinePlus documents to {args.output}")


def parse_medlineplus_xml(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    english_only: bool = True,
    max_documents: int | None = None,
) -> list[OfficialHealthDocument]:
    path = Path(input_path)
    documents: list[OfficialHealthDocument] = []
    seen_ids: set[str] = set()

    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag != "health-topic":
            continue
        if english_only and element.attrib.get("language") != "English":
            element.clear()
            continue

        document = medlineplus_topic_to_document(element)
        if document.id not in seen_ids:
            documents.append(document)
            seen_ids.add(document.id)

        element.clear()
        if max_documents is not None and len(documents) >= max_documents:
            break

    return documents


def medlineplus_topic_to_document(element: ET.Element) -> OfficialHealthDocument:
    title = _clean_text(element.attrib.get("title", "Untitled MedlinePlus topic"))
    url = element.attrib.get("url", "https://medlineplus.gov/")
    topic_id = element.attrib.get("id") or _slug(title)
    groups = [_clean_text(group.text or "") for group in element.findall("group")]
    summary = element.findtext("full-summary") or element.attrib.get("meta-desc") or title
    sections = build_sections(element, summary, groups)

    return OfficialHealthDocument(
        id=f"medlineplus_{_slug(topic_id)}_{_slug(title)}",
        source="MedlinePlus",
        url=url,
        title=title,
        topic=title.lower(),
        priority=infer_priority(title, groups, summary),
        symptom_group=infer_symptom_group(groups, title),
        page_last_reviewed=None,
        next_review_due=None,
        sections=sections,
    )


def build_sections(
    element: ET.Element,
    summary: str,
    groups: list[str],
) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    summary_text = html_fragment_to_text(summary)
    if summary_text:
        sections.append(
            DocumentSection(
                heading="Summary",
                content=summary_text,
                section_type=classify_medlineplus_section("Summary", summary_text),
            )
        )

    aliases = [_clean_text(alias.text or "") for alias in element.findall("also-called")]
    aliases = [alias for alias in aliases if alias]
    if aliases:
        sections.append(
            DocumentSection(
                heading="Also called",
                content="\n".join(f"- {alias}" for alias in aliases),
                section_type="aliases",
            )
        )

    if groups:
        sections.append(
            DocumentSection(
                heading="Topic groups",
                content="\n".join(f"- {group}" for group in groups),
                section_type="metadata",
            )
        )

    sites = extract_selected_sites(element)
    if sites:
        sections.append(
            DocumentSection(
                heading="Related official resources",
                content="\n".join(sites),
                section_type="metadata",
            )
        )

    if not sections:
        sections.append(
            DocumentSection(
                heading="Summary",
                content=_clean_text(element.attrib.get("meta-desc", element.attrib.get("title", "MedlinePlus topic"))),
                section_type="overview",
            )
        )

    return sections


def html_fragment_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    items: list[str] = []

    for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = _clean_text(element.get_text(" ", strip=True))
        if not text:
            continue
        prefix = "- " if element.name == "li" else ""
        items.append(f"{prefix}{text}")

    if not items:
        text = _clean_text(soup.get_text(" ", strip=True))
        if text:
            items.append(text)

    return "\n".join(_dedupe(items))


def extract_selected_sites(element: ET.Element, limit: int = 8) -> list[str]:
    selected: list[str] = []

    for site in element.findall("site"):
        category = _clean_text(site.findtext("information-category") or "")
        organization = _clean_text(site.findtext("organization") or "")
        title = _clean_text(site.attrib.get("title", ""))
        url = _clean_text(site.attrib.get("url", ""))
        if not title or not url:
            continue
        if category not in {"Learn More", "Patient Handouts", "Start Here", "Diagnosis and Tests", "Treatments and Therapies"}:
            continue
        label = f"- {title}"
        if organization:
            label = f"{label} ({organization})"
        selected.append(f"{label}: {url}")
        if len(selected) >= limit:
            break

    return selected


def classify_medlineplus_section(heading: str, content: str) -> str:
    text = f"{heading} {content}".lower()
    if any(marker in text for marker in ("call 911", "get medical help immediately", "emergency", "right away")):
        return "urgent_advice"
    if any(marker in text for marker in ("symptom", "signs include", "warning signs")):
        return "symptoms"
    if any(marker in text for marker in ("treatment", "treated", "medicine", "therapy")):
        return "treatment"
    if any(marker in text for marker in ("prevent", "prevention", "vaccine", "vaccination")):
        return "prevention"
    if "cause" in text:
        return "causes"
    return "overview"


def infer_priority(title: str, groups: list[str], summary: str) -> str:
    text = " ".join([title, summary, *groups]).lower()
    high_markers = (
        "call 911",
        "get medical help immediately",
        "emergency",
        "heart attack",
        "stroke",
        "sepsis",
        "anaphylaxis",
        "poisoning",
        "meningitis",
    )
    if any(marker in text for marker in high_markers):
        return "high"
    if any(group.lower() in {"symptoms", "infections", "injuries and wounds"} for group in groups):
        return "medium"
    return "medium"


def infer_symptom_group(groups: list[str], title: str) -> str:
    for group in groups:
        mapped = GROUP_TO_SYMPTOM_GROUP.get(group.lower())
        if mapped:
            return mapped

    lowered = title.lower()
    if any(marker in lowered for marker in ("cough", "asthma", "breathing", "pneumonia", "flu")):
        return "respiratory"
    if any(marker in lowered for marker in ("heart", "chest pain", "stroke", "blood pressure")):
        return "cardiovascular"
    if any(marker in lowered for marker in ("stomach", "abdominal", "diarrhea", "vomiting")):
        return "gastrointestinal"
    return "general"


def write_jsonl(path: str | Path, documents: list[OfficialHealthDocument]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    value = value.strip("_").lower()
    return value or "medlineplus"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--include-non-english", action="store_true")
    parser.add_argument("--max-documents", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
