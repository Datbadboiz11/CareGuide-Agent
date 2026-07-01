from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup, Tag

from careguide.schemas.document import DocumentSection, OfficialHealthDocument, OfficialSourceConfig


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCES_PATH = ROOT / "data" / "raw" / "official_sources" / "official_sources.yaml"
DEFAULT_HTML_DIR = ROOT / "data" / "raw" / "official_sources" / "html"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "processed" / "official_health_documents.jsonl"

SKIP_HEADINGS = {
    "contents",
    "support links",
    "help us improve our website",
    "find out more",
    "more information",
}


def main() -> None:
    args = _parse_args()
    sources = load_sources(args.sources)
    documents: list[OfficialHealthDocument] = []

    for index, source in enumerate(sources):
        if source.source != "NHS":
            continue
        html = load_or_fetch_html(
            source=source,
            html_dir=args.html_dir,
            use_cache=not args.no_cache,
            fetch=not args.parse_cached_only,
            timeout=args.timeout,
        )
        documents.append(parse_nhs_document(source, html))
        if index < len(sources) - 1 and not args.parse_cached_only:
            time.sleep(args.delay)

    write_jsonl(args.output, documents)
    print(f"Wrote {len(documents)} documents to {args.output}")


def load_sources(path: str | Path = DEFAULT_SOURCES_PATH) -> list[OfficialSourceConfig]:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected YAML mapping")

    nhs_sources = raw.get("nhs", [])
    if not isinstance(nhs_sources, list):
        raise ValueError(f"{path}: expected 'nhs' to be a list")

    return [OfficialSourceConfig.model_validate(item) for item in nhs_sources]


def load_or_fetch_html(
    source: OfficialSourceConfig,
    html_dir: str | Path = DEFAULT_HTML_DIR,
    use_cache: bool = True,
    fetch: bool = True,
    timeout: int = 30,
) -> str:
    cache_path = Path(html_dir) / f"{source.id}.html"
    if use_cache and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    if not fetch:
        raise FileNotFoundError(f"Cached HTML not found: {cache_path}")

    headers = {
        "User-Agent": "CareGuideAgent/0.1 educational project contact: local",
        "Accept": "text/html,application/xhtml+xml",
    }
    response = requests.get(str(source.url), headers=headers, timeout=timeout)
    response.raise_for_status()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def parse_nhs_document(source: OfficialSourceConfig, html: str) -> OfficialHealthDocument:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)
    sections = _extract_sections(soup)
    page_last_reviewed, next_review_due = _extract_review_dates(soup.get_text("\n", strip=True))

    return OfficialHealthDocument(
        id=source.id,
        source=source.source,
        url=source.url,
        title=title,
        topic=source.topic,
        priority=source.priority,
        symptom_group=source.symptom_group,
        page_last_reviewed=page_last_reviewed,
        next_review_due=next_review_due,
        sections=sections,
    )


def write_jsonl(path: str | Path, documents: list[OfficialHealthDocument]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return _clean_text(h1.get_text(" ", strip=True))
    if soup.title:
        return _clean_text(soup.title.get_text(" ", strip=True).replace("- NHS", ""))
    return "Untitled NHS page"


def _extract_sections(soup: BeautifulSoup) -> list[DocumentSection]:
    main = soup.find("main") or soup.body or soup
    headings = main.find_all(["h1", "h2", "h3"])
    sections: list[DocumentSection] = []
    seen: set[str] = set()

    for heading in headings:
        heading_text = _clean_heading(heading.get_text(" ", strip=True))
        if not heading_text or heading_text.lower() in SKIP_HEADINGS:
            continue
        content = _collect_section_content(heading)
        if not content:
            continue
        if heading_text in seen:
            continue
        sections.append(
            DocumentSection(
                heading=heading_text,
                content=content,
                section_type=_classify_section(heading_text),
            )
        )
        seen.add(heading_text)

    if not sections:
        fallback = _clean_text(main.get_text("\n", strip=True))
        if fallback:
            sections.append(
                DocumentSection(
                    heading="Overview",
                    content=fallback,
                    section_type="overview",
                )
            )

    return sections


def _collect_section_content(heading: Tag) -> str:
    items: list[str] = []
    for sibling in heading.find_next_siblings():
        if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3"}:
            break
        if not isinstance(sibling, Tag):
            continue
        if sibling.name in {"script", "style", "nav", "footer"}:
            continue
        if sibling.name in {"p", "li"}:
            text = _clean_text(sibling.get_text(" ", strip=True))
            if text:
                items.append(text)
        elif sibling.name in {"ul", "ol"}:
            for li in sibling.find_all("li", recursive=False):
                text = _clean_text(li.get_text(" ", strip=True))
                if text:
                    items.append(f"- {text}")
        elif sibling.name in {"div", "section"}:
            nested = _extract_nested_text(sibling)
            if nested:
                items.extend(nested)
    return "\n".join(_dedupe(items))


def _extract_nested_text(tag: Tag) -> list[str]:
    items: list[str] = []
    for child in tag.find_all(["p", "li"], recursive=True):
        text = _clean_text(child.get_text(" ", strip=True))
        if text and not _is_boilerplate(text):
            prefix = "- " if child.name == "li" else ""
            items.append(f"{prefix}{text}")
    return items


def _extract_review_dates(text: str) -> tuple[str | None, str | None]:
    last_reviewed = None
    next_review_due = None

    last_match = re.search(r"Page last reviewed:\s*([^\n]+)", text)
    if last_match:
        last_reviewed = _clean_text(last_match.group(1))

    next_match = re.search(r"Next review due:\s*([^\n]+)", text)
    if next_match:
        next_review_due = _clean_text(next_match.group(1))

    return last_reviewed, next_review_due


def _classify_section(heading: str) -> str:
    lowered = heading.lower()
    if "immediate action" in lowered or "call 999" in lowered or "a&e" in lowered:
        return "immediate_action"
    if "urgent advice" in lowered or "111" in lowered:
        return "urgent_advice"
    if "non-urgent advice" in lowered or "see a gp" in lowered:
        return "non_urgent_advice"
    if "symptom" in lowered:
        return "symptoms"
    if "treatment" in lowered:
        return "treatment"
    if "cause" in lowered:
        return "causes"
    if "ease" in lowered or "yourself" in lowered or "do" == lowered:
        return "self_care"
    return "overview"


def _clean_heading(text: str) -> str:
    text = _clean_text(text)
    text = re.sub(r"^(Overview\s*-\s*)", "", text, flags=re.IGNORECASE)
    return text


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "back to",
            "take our survey",
            "support links",
            "nhs app",
            "find my nhs number",
            "view your test results",
            "about the nhs",
            "accessibility statement",
            "cookies",
            "© crown copyright",
        )
    )


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen or _is_boilerplate(item):
            continue
        result.append(item)
        seen.add(item)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--html-dir", type=Path, default=DEFAULT_HTML_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--parse-cached-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
