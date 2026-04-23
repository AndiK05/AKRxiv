from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from src.models import PaperClassification
from src.utils import (
    INTERMEDIATE_DIR,
    OUTPUT_DIR,
    ensure_directory,
    ensure_output_files,
    load_classification_schema,
    load_json,
    load_profile,
    public_paper_record,
    sort_public_papers,
    write_json,
)

INPUT_PATH = INTERMEDIATE_DIR / "prefiltered.json"
ERROR_LOG_PATH = OUTPUT_DIR / "classification_errors.json"

PROMPT_CONTRACT = """You are classifying arXiv papers for a specific researcher.

Use only the provided metadata:
- title
- abstract
- categories
- authors
- comments if present

Do not invent claims not present in the abstract.
Do not assume a paper is novel just because it sounds ambitious.
Do not use outside knowledge.
Be conservative when confidence is low.

Return JSON matching the provided schema exactly.
Bucket definitions:
- recommended: likely worth active attention soon
- maybe: plausibly relevant but not clearly strong
- ignore: not worth attention for this profile
"""


def build_messages(profile: dict[str, Any], paper: dict[str, Any]) -> list[dict[str, str]]:
    thresholds = profile.get("thresholds", {})
    research_profile = profile.get("research_profile", "").strip()
    classification_policy = profile.get("classification_policy", "").strip()
    threshold_text = (
        "Scoring guidance:\n"
        f"- recommended is usually score >= {int(thresholds.get('recommended_min_score', 75))}\n"
        f"- maybe is usually score >= {int(thresholds.get('maybe_min_score', 50))}\n"
        "- scores below the maybe threshold should normally map to ignore"
    )
    system_message = "\n\n".join(
        part
        for part in (
            PROMPT_CONTRACT.strip(),
            "Research profile:\n" + research_profile,
            "Classification policy:\n" + classification_policy,
            threshold_text,
        )
        if part.strip()
    )

    paper_payload = {
        "paper_id": paper.get("paper_id"),
        "title": paper.get("title"),
        "abstract": paper.get("abstract"),
        "authors": paper.get("authors", []),
        "categories": paper.get("categories", []),
        "comment": paper.get("comment"),
    }

    return [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": "Classify this paper metadata:\n"
            + json.dumps(paper_payload, indent=2, ensure_ascii=False),
        },
    ]


def extract_refusal(response: Any) -> str | None:
    try:
        payload = response.model_dump()
    except AttributeError:
        return None

    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                return content.get("refusal")
    return None


def validate_classification(schema: dict[str, Any], result: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)


def classify_one_paper(
    client: OpenAI,
    profile: dict[str, Any],
    schema: dict[str, Any],
    paper: dict[str, Any],
) -> dict[str, Any]:
    model_policy = profile.get("model_policy", {})
    response = client.responses.create(
        model=model_policy.get("model", "gpt-5.4-mini"),
        input=build_messages(profile, paper),
        temperature=float(model_policy.get("temperature", 0.2)),
        reasoning={"effort": model_policy.get("reasoning_effort", "medium")},
        max_output_tokens=400,
        text={
            "format": {
                "type": "json_schema",
                "name": "paper_classification",
                "strict": True,
                "schema": schema,
            }
        },
    )

    output_text = getattr(response, "output_text", "") or ""
    if not output_text.strip():
        refusal = extract_refusal(response)
        if refusal:
            raise RuntimeError(f"Model refusal: {refusal}")
        raise RuntimeError("Model response did not contain structured output text.")

    result = json.loads(output_text)
    result["paper_id"] = paper["paper_id"]
    result["title"] = paper["title"]
    validate_classification(schema, result)
    return PaperClassification.from_dict(result).to_dict()


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required to classify papers.")

    ensure_directory(OUTPUT_DIR)
    ensure_output_files()

    profile = load_profile()
    schema = load_classification_schema()
    papers = load_json(INPUT_PATH, default=[])
    client = OpenAI(api_key=api_key)

    final_papers: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    retryable_exceptions = (APIConnectionError, APITimeoutError, RateLimitError, APIError)

    for paper in papers:
        for attempt in range(3):
            try:
                classification = classify_one_paper(client, profile, schema, paper)
                final_papers.append(public_paper_record(paper, classification))
                break
            except retryable_exceptions as exc:
                if attempt == 2:
                    errors.append(
                        {
                            "paper_id": paper.get("paper_id", ""),
                            "title": paper.get("title", ""),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                else:
                    time.sleep(2**attempt)
            except Exception as exc:
                errors.append(
                    {
                        "paper_id": paper.get("paper_id", ""),
                        "title": paper.get("title", ""),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                break

    final_papers = sort_public_papers(final_papers)
    recommended = [paper for paper in final_papers if paper["bucket"] == "recommended"]
    maybe = [paper for paper in final_papers if paper["bucket"] == "maybe"]
    ignored = [paper for paper in final_papers if paper["bucket"] == "ignore"]

    write_json(OUTPUT_DIR / "papers.json", final_papers)
    write_json(OUTPUT_DIR / "recommended.json", recommended)
    write_json(OUTPUT_DIR / "maybe.json", maybe)
    write_json(OUTPUT_DIR / "ignored.json", ignored)
    write_json(ERROR_LOG_PATH, errors)
    print(
        "Classified "
        f"{len(final_papers)} papers successfully; "
        f"{len(errors)} papers were logged as errors."
    )


if __name__ == "__main__":
    main()

