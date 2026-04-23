from __future__ import annotations

import shutil

from src.utils import (
    DIST_DIR,
    OUTPUT_DATA_FILES,
    OUTPUT_DIR,
    WEB_DIR,
    ensure_output_files,
    isoformat_z,
    load_json,
    utc_now,
    write_json,
    write_text,
)


def main() -> None:
    ensure_output_files()

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(WEB_DIR, DIST_DIR)

    dist_data_dir = DIST_DIR / "data"
    dist_data_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "generated_at": isoformat_z(utc_now()),
        "counts": {},
    }

    for filename in OUTPUT_DATA_FILES:
        records = load_json(OUTPUT_DIR / filename, default=[])
        write_json(dist_data_dir / filename, records)
        metadata["counts"][filename.replace(".json", "")] = len(records)

    write_json(dist_data_dir / "metadata.json", metadata)
    write_text(DIST_DIR / ".nojekyll", "")
    print(f"Built static site into {DIST_DIR}")


if __name__ == "__main__":
    main()

