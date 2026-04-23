from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
OUTPUT_DIR = DATA_DIR / "output"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = PROJECT_ROOT / "dist"

OUTPUT_DATA_FILES = (
    "papers.json",
    "recommended.json",
    "maybe.json",
    "ignored.json",
)

PUBLIC_PAPER_KEYS = (
    "paper_id",
    "title",
    "abstract",
    "authors",
    "categories",
    "published",
    "link_abs",
    "link_pdf",
    "bucket",
    "score",
    "confidence",
    "short_reason",
    "matched_topics",
    "concerns",
)

BUCKET_ORDER = {
    "recommended": 0,
    "maybe": 1,
    "ignore": 2,
}


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return [] if default is None else default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_profile() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "profile.yaml")


def load_sources() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "sources.yaml")


def load_classification_schema() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "schema.json", default={})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_whitespace(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_term(term: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (term or "").lower()).strip()


def normalize_text(parts: Iterable[str]) -> str:
    joined = " ".join(part for part in parts if part)
    return normalize_term(joined)


def matches_term(normalized_text: str, term: str) -> bool:
    candidate = normalize_term(term)
    return bool(candidate) and candidate in normalized_text


def sort_by_published_desc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            -parse_datetime(item.get("published", "")).timestamp(),
            item.get("paper_id", ""),
        ),
    )


def sort_public_papers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            BUCKET_ORDER.get(item.get("bucket", "ignore"), 99),
            -int(item.get("score", 0)),
            -parse_datetime(item.get("published", "")).timestamp(),
            item.get("paper_id", ""),
        ),
    )


def public_paper_record(
    paper: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        "paper_id": paper["paper_id"],
        "title": paper["title"],
        "abstract": paper.get("abstract", ""),
        "authors": list(paper.get("authors", [])),
        "categories": list(paper.get("categories", [])),
        "published": paper.get("published", ""),
        "link_abs": paper.get("link_abs", ""),
        "link_pdf": paper.get("link_pdf", ""),
        "bucket": classification["bucket"],
        "score": int(classification["score"]),
        "confidence": float(classification["confidence"]),
        "short_reason": classification["short_reason"],
        "matched_topics": list(classification.get("matched_topics", [])),
        "concerns": list(classification.get("concerns", [])),
    }
    return {key: merged[key] for key in PUBLIC_PAPER_KEYS}


def ensure_output_files() -> None:
    ensure_directory(OUTPUT_DIR)
    for filename in OUTPUT_DATA_FILES:
        path = OUTPUT_DIR / filename
        if not path.exists():
            write_json(path, [])
