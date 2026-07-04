from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from careguide.schemas.document import DocumentSection, OfficialHealthDocument


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUERIES_PATH = ROOT / "data" / "raw" / "official_sources" / "cdc_queries.yaml"
DEFAULT_CACHE_DIR = ROOT / "data" / "raw" / "official_sources" / "cdc"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "processed" / "cdc_documents.jsonl"
CDC_API_BASE = "https://tools.cdc.gov/api"


class CdcQueryConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    symptom_group: str = Field(min_length=1)
    priority: str = "medium"
    max_results: int = Field(default=10, ge=1)


class CdcMediaRecord(BaseModel):

    model_config = ConfigDict(extra="forbid")

    media_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    description: str | None = None
    html_content: str | None = None


class CdcPageConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    url: HttpUrl
    title: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    symptom_group: str = Field(min_length=1)
    priority: str = "medium"


def main() -> None:
    args = _parse_args()
    queries = load_cdc_queries(args.queries)
    pages = load_cdc_pages(args.queries)
    documents: list[OfficialHealthDocument] = []
    seen_media_ids: set[str] = set()
    seen_urls: set[str] = set()
    errors: list[str] = []

    for query_config in queries:
        try:
            payload = load_or_fetch_search_payload(
                query_config=query_config,
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                fetch=not args.parse_cached_only,
                timeout=args.timeout,
            )
            media_records = extract_media_records(payload)[: query_config.max_results]
        except Exception as exc:
            if args.fail_fast:
                raise
            errors.append(f"search {query_config.query}: {exc}")
            print(f"SKIP search {query_config.query}: {exc}")
            continue

        for media_record in media_records:
            if media_record.media_id in seen_media_ids:
                continue
            try:
                enriched = enrich_media_record(
                    media_record=media_record,
                    cache_dir=args.cache_dir,
                    use_cache=not args.no_cache,
                    fetch=not args.parse_cached_only,
                    timeout=args.timeout,
                )
                documents.append(cdc_media_to_document(query_config, enriched))
                seen_media_ids.add(media_record.media_id)
                seen_urls.add(str(enriched.url))
            except Exception as exc:
                if args.fail_fast:
                    raise
                errors.append(f"media {media_record.media_id}: {exc}")
                print(f"SKIP media {media_record.media_id}: {exc}")

            if not args.parse_cached_only:
                time.sleep(args.delay)

    for page_config in pages:
        if str(page_config.url) in seen_urls:
            continue
        try:
            html = load_or_fetch_page_html(
                page_config=page_config,
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                fetch=not args.parse_cached_only,
                timeout=args.timeout,
            )
            documents.append(cdc_page_to_document(page_config, html))
            seen_urls.add(str(page_config.url))
        except Exception as exc:
            if args.fail_fast:
                raise
            errors.append(f"page {page_config.id}: {exc}")
            print(f"SKIP page {page_config.id}: {exc}")

        if not args.parse_cached_only:
            time.sleep(args.delay)

    write_jsonl(args.output, documents)
    print(f"Wrote {len(documents)} CDC documents to {args.output}")
    if errors:
        print(f"Skipped {len(errors)} CDC records with errors")


def load_cdc_queries(path: str | Path = DEFAULT_QUERIES_PATH) -> list[CdcQueryConfig]:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, dict) or not isinstance(raw.get("queries"), list):
        raise ValueError(f"{path}: expected queries list")

    return [CdcQueryConfig.model_validate(item) for item in raw["queries"]]


def load_cdc_pages(path: str | Path = DEFAULT_QUERIES_PATH) -> list[CdcPageConfig]:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    pages = raw.get("pages", []) if isinstance(raw, dict) else []
    if not isinstance(pages, list):
        raise ValueError(f"{path}: expected pages list")

    return [CdcPageConfig.model_validate(item) for item in pages]


def load_or_fetch_search_payload(
    query_config: CdcQueryConfig,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    fetch: bool = True,
    timeout: int = 30,
) -> dict[str, Any]:
    cache_path = Path(cache_dir) / "search" / f"{_slug(query_config.query)}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    if not fetch:
        raise FileNotFoundError(f"Cached CDC search payload not found: {cache_path}")

    payload = fetch_json(
        f"{CDC_API_BASE}/v2/resources/media",
        params={"q": query_config.query, "max": query_config.max_results},
        timeout=timeout,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def enrich_media_record(
    media_record: CdcMediaRecord,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    fetch: bool = True,
    timeout: int = 30,
) -> CdcMediaRecord:
    cache_path = Path(cache_dir) / "content" / f"{_slug(media_record.media_id)}.json"
    payload: dict[str, Any] | None = None

    if use_cache and cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    elif fetch:
        payload = fetch_json(
            f"{CDC_API_BASE}/v2/resources/media/{media_record.media_id}/content",
            timeout=timeout,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not payload:
        return media_record

    html = extract_content_html(payload)
    if not html:
        return media_record

    return CdcMediaRecord(
        media_id=media_record.media_id,
        title=media_record.title,
        url=media_record.url,
        description=media_record.description,
        html_content=html,
    )


def load_or_fetch_page_html(
    page_config: CdcPageConfig,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    fetch: bool = True,
    timeout: int = 30,
) -> str:
    cache_path = Path(cache_dir) / "pages" / f"{page_config.id}.html"
    if use_cache and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    if not fetch:
        raise FileNotFoundError(f"Cached CDC page HTML not found: {cache_path}")

    html = fetch_text(str(page_config.url), timeout=timeout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "CareGuideAgent/0.1 educational project contact: local",
        "Accept": "application/json",
    }
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{url}: expected JSON object")
    return payload


def fetch_text(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "CareGuideAgent/0.1 educational project contact: local",
        "Accept": "text/html,application/xhtml+xml",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def extract_media_records(payload: dict[str, Any]) -> list[CdcMediaRecord]:
    raw_items = _find_media_items(payload)
    records: list[CdcMediaRecord] = []
    seen: set[str] = set()

    for item in raw_items:
        media_id = _first_value(item, ("mediaId", "mediaID", "id", "media_id", "MediaId"))
        title = _first_value(item, ("name", "title", "Title", "mediaName"))
        url = _first_value(item, ("sourceUrl", "targetUrl", "url", "link", "Url"))
        description = _first_value(item, ("description", "summary", "Description"))

        if not media_id or not title:
            continue
        if not url:
            url = f"https://tools.cdc.gov/api/v2/resources/media/{media_id}"
        if media_id in seen:
            continue

        records.append(
            CdcMediaRecord.model_validate(
                {
                    "media_id": str(media_id),
                    "title": str(title),
                    "url": str(url),
                    "description": str(description) if description else None,
                    "html_content": None,
                }
            )
        )
        seen.add(media_id)

    return records


def extract_content_html(payload: dict[str, Any]) -> str | None:
    candidate = _first_value(
        payload,
        (
            "content",
            "Content",
            "html",
            "Html",
            "body",
            "Body",
            "embedCode",
            "EmbedCode",
        ),
    )
    if candidate:
        return str(candidate)

    results = payload.get("results") or payload.get("Results") or payload.get("result")
    if isinstance(results, list) and results:
        return extract_content_html(results[0]) if isinstance(results[0], dict) else None
    if isinstance(results, dict):
        return extract_content_html(results)

    return None


def cdc_media_to_document(
    query_config: CdcQueryConfig,
    media_record: CdcMediaRecord,
) -> OfficialHealthDocument:
    sections = sections_from_cdc_media(media_record)
    return OfficialHealthDocument(
        id=f"cdc_{_slug(media_record.media_id)}",
        source="CDC",
        url=media_record.url,
        title=media_record.title,
        topic=query_config.topic,
        priority=query_config.priority,
        symptom_group=query_config.symptom_group,
        page_last_reviewed=None,
        next_review_due=None,
        sections=sections,
    )


def cdc_page_to_document(
    page_config: CdcPageConfig,
    html: str,
) -> OfficialHealthDocument:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup) or page_config.title
    sections = sections_from_cdc_html(html)

    return OfficialHealthDocument(
        id=page_config.id,
        source="CDC",
        url=page_config.url,
        title=title,
        topic=page_config.topic,
        priority=page_config.priority,
        symptom_group=page_config.symptom_group,
        page_last_reviewed=_extract_cdc_date(soup),
        next_review_due=None,
        sections=sections,
    )


def sections_from_cdc_media(media_record: CdcMediaRecord) -> list[DocumentSection]:
    sections: list[DocumentSection] = []

    if media_record.description:
        sections.append(
            DocumentSection(
                heading="Summary",
                content=_clean_text(media_record.description),
                section_type="overview",
            )
        )

    if media_record.html_content:
        content = html_to_text(media_record.html_content)
        if content:
            sections.append(
                DocumentSection(
                    heading="CDC content",
                    content=content,
                    section_type=classify_cdc_section(media_record.title, content),
                )
            )

    if not sections:
        sections.append(
            DocumentSection(
                heading="CDC media",
                content=media_record.title,
                section_type="overview",
            )
        )

    return sections


def sections_from_cdc_html(html: str) -> list[DocumentSection]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body or soup
    headings = main.find_all(["h1", "h2", "h3"])
    sections: list[DocumentSection] = []
    seen: set[str] = set()

    for heading in headings:
        heading_text = _clean_text(heading.get_text(" ", strip=True))
        if not heading_text or heading_text.lower() in {"on this page", "related topics"}:
            continue
        content = _collect_until_next_heading(heading)
        if not content:
            continue
        if heading_text in seen:
            continue
        sections.append(
            DocumentSection(
                heading=heading_text,
                content=content,
                section_type=classify_cdc_section(heading_text, content),
            )
        )
        seen.add(heading_text)

    if not sections:
        content = html_to_text(html)
        if content:
            sections.append(
                DocumentSection(
                    heading="CDC content",
                    content=content,
                    section_type=classify_cdc_section("", content),
                )
            )

    return sections


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
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


def _collect_until_next_heading(heading: Any) -> str:
    items: list[str] = []
    for sibling in heading.find_next_siblings():
        if getattr(sibling, "name", None) in {"h1", "h2", "h3"}:
            break
        if getattr(sibling, "name", None) in {"script", "style", "nav", "footer"}:
            continue
        if getattr(sibling, "name", None) in {"p", "li"}:
            text = _clean_text(sibling.get_text(" ", strip=True))
            if text:
                items.append(text if sibling.name != "li" else f"- {text}")
            continue
        if getattr(sibling, "name", None) in {"ul", "ol", "div", "section"}:
            nested = _nested_text(sibling)
            if nested:
                items.extend(nested)

    return "\n".join(_dedupe(items))


def _nested_text(tag: Any) -> list[str]:
    items: list[str] = []
    for child in tag.find_all(["p", "li"], recursive=True):
        text = _clean_text(child.get_text(" ", strip=True))
        if not text:
            continue
        items.append(text if child.name != "li" else f"- {text}")
    return items


def classify_cdc_section(title: str, content: str) -> str:
    text = f"{title} {content}".lower()
    if any(marker in text for marker in ("emergency", "call 911", "warning signs", "seek medical care")):
        return "urgent_advice"
    if any(marker in text for marker in ("symptom", "signs")):
        return "symptoms"
    if any(marker in text for marker in ("prevent", "prevention", "vaccine", "vaccination")):
        return "prevention"
    if any(marker in text for marker in ("treatment", "treated", "medicine")):
        return "treatment"
    return "overview"


def write_jsonl(path: str | Path, documents: list[OfficialHealthDocument]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _find_media_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "Results", "result", "Result", "media", "Media", "items", "Items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _find_media_items(value)
            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, dict):
            nested = _find_media_items(value)
            if nested:
                return nested
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value

    return []


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_title(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1:
        return _clean_text(h1.get_text(" ", strip=True))
    if soup.title:
        return _clean_text(soup.title.get_text(" ", strip=True).replace("| CDC", "").replace("CDC", ""))
    return None


def _extract_cdc_date(soup: BeautifulSoup) -> str | None:
    text = soup.get_text("\n", strip=True)
    match = re.search(
        r"\b(?:Jan\.?|Feb\.?|Mar\.?|Apr\.?|May|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Oct\.?|Nov\.?|Dec\.?)\s+\d{1,2},\s+\d{4}\b",
        text,
    )
    return match.group(0) if match else None


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
    return value or "cdc"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--parse-cached-only", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
