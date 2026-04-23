from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class CandidatePaper:
    paper_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    published: str
    updated: str
    link_abs: str
    link_pdf: str
    comment: str | None = None
    source_queries: list[str] = field(default_factory=list)
    prefilter_score: int | None = None
    prefilter_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidatePaper":
        return cls(
            paper_id=data["paper_id"],
            title=data["title"],
            abstract=data.get("abstract", ""),
            authors=list(data.get("authors", [])),
            categories=list(data.get("categories", [])),
            published=data.get("published", ""),
            updated=data.get("updated", data.get("published", "")),
            link_abs=data.get("link_abs", ""),
            link_pdf=data.get("link_pdf", ""),
            comment=data.get("comment"),
            source_queries=list(data.get("source_queries", [])),
            prefilter_score=data.get("prefilter_score"),
            prefilter_notes=list(data.get("prefilter_notes", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.comment is None:
            data.pop("comment")
        if not self.source_queries:
            data.pop("source_queries")
        if self.prefilter_score is None:
            data.pop("prefilter_score")
        if not self.prefilter_notes:
            data.pop("prefilter_notes")
        return data


@dataclass(slots=True)
class PaperClassification:
    paper_id: str
    title: str
    bucket: str
    score: int
    confidence: float
    short_reason: str
    matched_topics: list[str]
    concerns: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaperClassification":
        return cls(
            paper_id=data["paper_id"],
            title=data["title"],
            bucket=data["bucket"],
            score=int(data["score"]),
            confidence=float(data["confidence"]),
            short_reason=data["short_reason"],
            matched_topics=list(data.get("matched_topics", [])),
            concerns=list(data.get("concerns", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

