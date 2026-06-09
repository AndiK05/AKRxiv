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
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_MODEL = "openrouter/free"
DEFAULT_MAX_TOKENS = 400

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


def validate_classification(schema: dict[str, Any], result: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)


def extract_chat_content(response: Any) -> str:
    choices = getattr(response, "choices", []) or []
    if not choices:
        raise RuntimeError("Model response did not contain any choices.")

    message = choices[0].message
    refusal = getattr(message, "refusal", None)
    if refusal:
        raise RuntimeError(f"Model refusal: {refusal}")

    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(getattr(part, "text", "")))
        content = "".join(parts)

    if not str(content).strip():
        raise RuntimeError("Model response did not contain structured output text.")
    return str(content)


def classify_one_paper(
    client: OpenAI,
    profile: dict[str, Any],
    schema: dict[str, Any],
    paper: dict[str, Any],
) -> dict[str, Any]:
    model_policy = profile.get("model_policy", {})
    request_payload: dict[str, Any] = {
        "model": model_policy.get("model", DEFAULT_MODEL),
        "messages": build_messages(profile, paper),
        "temperature": float(model_policy.get("temperature", 0.2)),
        "max_tokens": int(
            model_policy.get(
                "max_tokens",
                model_policy.get("max_output_tokens", DEFAULT_MAX_TOKENS),
            )
        ),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "paper_classification",
                "strict": True,
                "schema": schema,
            }
        },
    }
    response = client.chat.completions.create(**request_payload)

    result = json.loads(extract_chat_content(response))
    result["paper_id"] = paper["paper_id"]
    result["title"] = paper["title"]
    validate_classification(schema, result)
    return PaperClassification.from_dict(result).to_dict()


def main() -> None:
    api_key = os.environ.get(OPENROUTER_API_KEY_ENV)
    if not api_key:
        raise SystemExit(f"{OPENROUTER_API_KEY_ENV} is required to classify papers.")

    ensure_directory(OUTPUT_DIR)
    ensure_output_files()

    profile = load_profile()
    schema = load_classification_schema()
    papers = load_json(INPUT_PATH, default=[])
    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

    final_papers: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    retryable_exceptions = (APIConnectionError, APITimeoutError, RateLimitError, APIError)

    total_papers = len(papers)
    print(f"Classifying {total_papers} papers...")

    for index, paper in enumerate(papers, start=1):
        paper_id = paper.get("paper_id", "")
        title = paper.get("title", "")
        print(f"[{index}/{total_papers}] Classifying {paper_id} - {title}")
        for attempt in range(3):
            try:
                classification = classify_one_paper(client, profile, schema, paper)
                final_papers.append(public_paper_record(paper, classification))
                print(
                    f"[{index}/{total_papers}] Success: "
                    f"{paper_id} -> {classification['bucket']} ({classification['score']})"
                )
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
                    print(
                        f"[{index}/{total_papers}] Failed after retries: "
                        f"{paper_id} -> {type(exc).__name__}: {exc}"
                    )
                else:
                    print(
                        f"[{index}/{total_papers}] Retry {attempt + 1}/2 for "
                        f"{paper_id}: {type(exc).__name__}: {exc}"
                    )
                    time.sleep(2**attempt)
            except Exception as exc:
                errors.append(
                    {
                        "paper_id": paper.get("paper_id", ""),
                        "title": paper.get("title", ""),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(
                    f"[{index}/{total_papers}] Failed: "
                    f"{paper_id} -> {type(exc).__name__}: {exc}"
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
