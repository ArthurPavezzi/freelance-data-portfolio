from __future__ import annotations

from pathlib import Path

import polars as pl

from .resolve import (
    build_manual_review_queue,
    resolve_matches,
)

DATA_DIR = Path("data/synthetic/crm")

OUTPUT_DIR = Path("data/processed/reconciliation")


def main() -> None:
    exact_matches = pl.read_parquet(OUTPUT_DIR / "exact_matches.parquet")

    fuzzy_candidates = pl.read_parquet(OUTPUT_DIR / "fuzzy_candidates.parquet")

    resolved = resolve_matches(
        exact_matches,
        fuzzy_candidates,
    )

    review_queue = build_manual_review_queue(fuzzy_candidates)

    resolved.write_parquet(OUTPUT_DIR / "reconciliation_results.parquet")

    review_queue.write_csv(OUTPUT_DIR / "manual_review_queue.csv")

    print("Final reconciliation resolution")

    print()

    print("=== RESOLUTION COUNTS ===")

    print(
        resolved.group_by(
            "match_method",
            "review_status",
        )
        .len()
        .sort(
            [
                "match_method",
                "review_status",
            ]
        )
    )

    print()

    print(
        "Manual-review candidates:",
        f"{review_queue.height:,}",
    )


if __name__ == "__main__":
    main()
