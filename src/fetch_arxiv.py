from __future__ import annotations

import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Any

import requests

from src.models import CandidatePaper
from src.utils import (
    INTERMEDIATE_DIR,
    RAW_DIR,
    ensure_directory,
    load_profile,
    load_sources,
    normalize_whitespace,
    parse_datetime,
    sort_by_published_desc,
    utc_now,
    write_json,
    write_text,
)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
REQUEST_TIMEOUT_SECONDS = 30
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
USER_AGENT = "AKRxiv/0.1 (+https://github.com/AndiK05/AKRxiv)"


def extract_paper_id(entry_id: str) -> str:
    parsed = urllib.parse.urlparse(entry_id)
    identifier = parsed.path.removeprefix("/abs/").lstrip("/")
    return re.sub(r"v\d+$", "", identifier)


def fetch_query_page(
    session: requests.Session,
    query: str,
    start: int,
    max_results: int,
    sort_by: str,
    sort_order: str,
) -> str:
    response = session.get(
        ARXIV_API_URL,
        params={
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.text


def parse_entry(entry: ET.Element, source_query: str) -> CandidatePaper | None:
    entry_id = normalize_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
    paper_id = extract_paper_id(entry_id)
    if not paper_id:
        return None

    title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    abstract = normalize_whitespace(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
    published = normalize_whitespace(
        entry.findtext("atom:published", default="", namespaces=ATOM_NS)
    )
    updated = normalize_whitespace(
        entry.findtext("atom:updated", default=published, namespaces=ATOM_NS)
    )
    authors = [
        normalize_whitespace(author.findtext("atom:name", default="", namespaces=ATOM_NS))
        for author in entry.findall("atom:author", ATOM_NS)
        if normalize_whitespace(author.findtext("atom:name", default="", namespaces=ATOM_NS))
    ]
    categories = sorted(
        {
            category.attrib.get("term", "").strip()
            for category in entry.findall("atom:category", ATOM_NS)
            if category.attrib.get("term")
        }
    )
    comment = normalize_whitespace(
        entry.findtext("arxiv:comment", default="", namespaces=ATOM_NS)
    )

    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        published=published,
        updated=updated,
        link_abs=f"https://arxiv.org/abs/{paper_id}",
        link_pdf=f"https://arxiv.org/pdf/{paper_id}.pdf",
        comment=comment or None,
        source_queries=[source_query],
    )


def parse_feed(xml_text: str, source_query: str) -> list[CandidatePaper]:
    root = ET.fromstring(xml_text)
    candidates: list[CandidatePaper] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        candidate = parse_entry(entry, source_query)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def merge_candidate(existing: dict[str, Any], incoming: CandidatePaper) -> dict[str, Any]:
    merged = dict(existing)
    merged["authors"] = sorted({*merged.get("authors", []), *incoming.authors})
    merged["categories"] = sorted({*merged.get("categories", []), *incoming.categories})
    merged["source_queries"] = sorted(
        {*merged.get("source_queries", []), *incoming.source_queries}
    )
    if not merged.get("comment") and incoming.comment:
        merged["comment"] = incoming.comment

    incoming_updated = parse_datetime(incoming.updated)
    existing_updated = parse_datetime(merged.get("updated", ""))
    if incoming_updated > existing_updated:
        merged["updated"] = incoming.updated

    return merged


def main() -> None:
    profile = load_profile()
    sources = load_sources()

    paper_window = profile.get("paper_window", {})
    days_back = int(paper_window.get("days_back", 3))
    max_candidates = int(paper_window.get("max_candidates_per_run", 120))

    queries = list(sources.get("queries", []))
    page_size = int(sources.get("page_size", 100))
    max_pages = int(sources.get("max_pages", 1))
    request_delay_seconds = float(sources.get("request_delay_seconds", 3))
    sort_by = sources.get("sort_by", "submittedDate")
    sort_order = sources.get("sort_order", "descending")

    ensure_directory(RAW_DIR)
    ensure_directory(INTERMEDIATE_DIR)

    session = requests.Session()
    deduped: dict[str, dict[str, Any]] = {}
    raw_snapshot_written = False
    request_count = 0

    for query in queries:
        for page_index in range(max_pages):
            if request_count:
                time.sleep(request_delay_seconds)

            start = page_index * page_size
            xml_text = fetch_query_page(
                session=session,
                query=query,
                start=start,
                max_results=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            request_count += 1

            if not raw_snapshot_written:
                write_text(RAW_DIR / "latest_arxiv.xml", xml_text)
                raw_snapshot_written = True

            for candidate in parse_feed(xml_text, source_query=query):
                if candidate.paper_id in deduped:
                    deduped[candidate.paper_id] = merge_candidate(
                        deduped[candidate.paper_id],
                        candidate,
                    )
                else:
                    deduped[candidate.paper_id] = candidate.to_dict()

    cutoff = utc_now() - timedelta(days=days_back)
    recent_candidates = [
        paper
        for paper in deduped.values()
        if parse_datetime(paper.get("published", "")) >= cutoff
    ]
    recent_candidates = sort_by_published_desc(recent_candidates)[:max_candidates]

    if not raw_snapshot_written:
        write_text(RAW_DIR / "latest_arxiv.xml", "")

    write_json(INTERMEDIATE_DIR / "candidates.json", recent_candidates)
    print(f"Fetched {len(recent_candidates)} recent unique candidate papers.")


if __name__ == "__main__":
    main()

