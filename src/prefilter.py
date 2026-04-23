from __future__ import annotations

from typing import Any

from src.utils import (
    INTERMEDIATE_DIR,
    load_json,
    load_profile,
    matches_term,
    normalize_text,
    parse_datetime,
    write_json,
)

INPUT_PATH = INTERMEDIATE_DIR / "candidates.json"
OUTPUT_PATH = INTERMEDIATE_DIR / "prefiltered.json"


def analyze_paper(paper: dict[str, Any], config: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    normalized = normalize_text(
        [
            paper.get("title", ""),
            paper.get("abstract", ""),
            " ".join(paper.get("categories", [])),
        ]
    )

    require_terms = list(config.get("require_any", []))
    exclude_terms = list(config.get("exclude_if_any", []))
    boost_terms = list(config.get("boost_if_any", []))

    matched_require = [term for term in require_terms if matches_term(normalized, term)]
    matched_exclude = [term for term in exclude_terms if matches_term(normalized, term)]
    matched_boost = [term for term in boost_terms if matches_term(normalized, term)]

    score = (len(matched_require) * 12) + (len(matched_boost) * 18) - (len(matched_exclude) * 30)
    strong_positive_override = len(matched_boost) >= 2 or score >= 40
    should_keep = bool(matched_require) and (not matched_exclude or strong_positive_override)

    notes: list[str] = []
    if matched_require:
        notes.append(f"Matched required terms: {', '.join(matched_require)}")
    if matched_boost:
        notes.append(f"Boost terms: {', '.join(matched_boost)}")
    if matched_exclude and strong_positive_override:
        notes.append(
            f"Exclude terms overridden by stronger signals: {', '.join(matched_exclude)}"
        )
    elif matched_exclude:
        notes.append(f"Dropped because of exclude terms: {', '.join(matched_exclude)}")

    enriched = dict(paper)
    enriched["prefilter_score"] = score
    enriched["prefilter_notes"] = notes
    return should_keep, enriched


def main() -> None:
    profile = load_profile()
    paper_window = profile.get("paper_window", {})
    max_llm_candidates = int(paper_window.get("max_llm_candidates_per_run", 40))
    prefilter_config = profile.get("prefilter", {})

    candidates = load_json(INPUT_PATH, default=[])
    kept: list[dict[str, Any]] = []

    for paper in candidates:
        should_keep, enriched = analyze_paper(paper, prefilter_config)
        if should_keep:
            kept.append(enriched)

    kept.sort(
        key=lambda paper: (
            paper.get("prefilter_score", 0),
            parse_datetime(paper.get("published", "")).timestamp(),
            paper.get("paper_id", ""),
        ),
        reverse=True,
    )
    kept = kept[:max_llm_candidates]

    write_json(OUTPUT_PATH, kept)
    print(f"Prefilter kept {len(kept)} papers for LLM classification.")


if __name__ == "__main__":
    main()

