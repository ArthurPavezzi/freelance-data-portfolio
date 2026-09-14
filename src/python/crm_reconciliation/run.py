from __future__ import annotations

from pathlib import Path

import polars as pl

from .evaluate import evaluate_matches
from .match import generate_exact_candidates
from .normalize import (
    prepare_crm,
    prepare_marketing,
)


DATA_DIR = Path(
    "data/synthetic/crm"
)

RAW_DIR = (
    DATA_DIR / "raw_exports"
)

TRUTH_DIR = (
    DATA_DIR / "ground_truth"
)

OUTPUT_DIR = Path(
    "data/processed/reconciliation"
)


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

    crm_map = pl.read_parquet(
        TRUTH_DIR
        / "crm_observation_map.parquet"
    )

    marketing_map = pl.read_parquet(
        TRUTH_DIR
        / "marketing_observation_map.parquet"
    )

    crm_clean = prepare_crm(
        crm
    )

    marketing_clean = (
        prepare_marketing(
            marketing
        )
    )

    matches = (
        generate_exact_candidates(
            crm_clean,
            marketing_clean,
        )
    )

    metrics, evaluated = (
        evaluate_matches(
            matches,
            crm_map,
            marketing_map,
        )
    )

    matches.write_parquet(
        OUTPUT_DIR
        / "exact_matches.parquet"
    )

    evaluated.write_parquet(
        OUTPUT_DIR
        / "exact_matches_evaluated.parquet"
    )

    print(
        "Cross-system lead reconciliation"
    )
    print()

    for key, value in metrics.items():
        if isinstance(
            value,
            float,
        ):
            print(
                f"{key}: {value:.4f}"
            )
        else:
            print(
                f"{key}: {value:,}"
            )


if __name__ == "__main__":
    main()
