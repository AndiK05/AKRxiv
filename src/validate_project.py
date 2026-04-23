from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from src.utils import OUTPUT_DATA_FILES, OUTPUT_DIR, load_classification_schema, load_json

PUBLIC_PAPER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "paper_id": {"type": "string"},
        "title": {"type": "string"},
        "abstract": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "categories": {"type": "array", "items": {"type": "string"}},
        "published": {"type": "string"},
        "link_abs": {"type": "string"},
        "link_pdf": {"type": "string"},
        "bucket": {
            "type": "string",
            "enum": ["recommended", "maybe", "ignore"],
        },
        "score": {"type": "integer"},
        "confidence": {"type": "number"},
        "short_reason": {"type": "string"},
        "matched_topics": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
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
    ],
}


def validate_records(name: str, records: Any, validator: Draft202012Validator) -> None:
    if not isinstance(records, list):
        raise TypeError(f"{name} must contain a JSON array.")
    for record in records:
        validator.validate(record)


def main() -> None:
    Draft202012Validator.check_schema(load_classification_schema())
    public_validator = Draft202012Validator(PUBLIC_PAPER_SCHEMA)

    for filename in OUTPUT_DATA_FILES:
        validate_records(
            filename,
            load_json(OUTPUT_DIR / filename, default=[]),
            public_validator,
        )

    print("Project validation passed.")


if __name__ == "__main__":
    main()

