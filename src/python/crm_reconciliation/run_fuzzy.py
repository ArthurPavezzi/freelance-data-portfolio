from __future__ import annotations

from pathlib import Path

import polars as pl

from .fuzzy import (
    generate_fuzzy_candidates,
    score_fuzzy_candidates,
)

DATA_DIR = Path("data/synthetic/crm")

RAW_DIR = DATA_DIR / "raw_exports"

OUTPUT_DIR = Path("data/processed/reconciliation")


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    crm = pl.read_csv(
        RAW_DIR / "crm_leads.csv",
        try_parse_dates=True,
    )

    marketing = pl.read_csv(
        RAW_DIR / "marketing_leads.csv",
        try_parse_dates=True,
    )

    exact_matches = pl.read_parquet(
        OUTPUT_DIR
        / "exact_matches.parquet"
    )

    candidates = (
        generate_fuzzy_candidates(
            crm,
            marketing,
            exact_matches,
        )
    )

    scored = (
        score_fuzzy_candidates(
            candidates
        )
    )

    scored.write_parquet(
        OUTPUT_DIR / "fuzzy_candidates.parquet"
    )

    print("Fuzzy candidate generation")
    print()

    print(
        "candidate_pairs:",
        f"{candidates.height:,}",
    )

    print(
        "crm_records:",
        f"{crm.height:,}",
    )

    print(
        "marketing_records:",
        f"{marketing.height:,}",
    )

    print()
    print("Score distribution:")

    print(
        scored.select(
            pl.col("fuzzy_score")
            .min()
            .alias("min"),

            pl.col("fuzzy_score")
            .quantile(0.25)
            .alias("p25"),

            pl.col("fuzzy_score")
            .median()
            .alias("median"),

            pl.col("fuzzy_score")
            .quantile(0.75)
            .alias("p75"),

            pl.col("fuzzy_score")
            .quantile(0.90)
            .alias("p90"),

            pl.col("fuzzy_score")
            .quantile(0.95)
            .alias("p95"),

            pl.col("fuzzy_score")
            .quantile(0.99)
            .alias("p99"),

            pl.col("fuzzy_score")
            .max()
            .alias("max"),
        )
    )


if __name__ == "__main__":
    main()
