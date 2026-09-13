from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from .validation import (
    build_internal_validation,
    validation_summary_frame,
)

RAW_DIR = Path(
    "data/synthetic/crm/raw_exports"
)

TRUTH_DIR = Path(
    "data/synthetic/crm/ground_truth"
)

PROCESSED_DIR = Path(
    "data/processed/reconciliation"
)

VALIDATION_DIR = Path(
    "reports/reconciliation/internal_validation"
)


def main() -> None:
    VALIDATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    universe = pl.read_parquet(
        PROCESSED_DIR
        / "reconstructed_acquisition_universe.parquet"
    )

    confirmed_membership = (
        pl.read_parquet(
            PROCESSED_DIR
            / "reconciled_record_membership.parquet"
        )
    )

    singleton_membership = (
        pl.read_parquet(
            PROCESSED_DIR
            / "deduped_singleton_membership.parquet"
        )
    )

    crm_map = pl.read_parquet(
        TRUTH_DIR
        / "crm_observation_map.parquet"
    )

    marketing_map = pl.read_parquet(
        TRUTH_DIR
        / "marketing_observation_map.parquet"
    )

    leads = pl.read_parquet(
        TRUTH_DIR
        / "leads.parquet"
    )

    spend = pl.read_csv(
        RAW_DIR
        / "marketing_spend.csv",
        try_parse_dates=True,
    )

    (
        summary,
        entity_validation,
        source_validation,
        paid_validation,
    ) = build_internal_validation(
        universe,
        confirmed_membership,
        singleton_membership,
        crm_map,
        marketing_map,
        leads,
        spend,
    )

    summary_frame = pl.DataFrame(
        {
            "metric": list(
                summary.keys()
            ),
            "value": pl.Series(
                "value",
                [
                    float(value)
                    for value in summary.values()
                ],
                dtype=pl.Float64,
            ),
        }
    )
    
    summary_frame.write_csv(
        VALIDATION_DIR
        / "benchmark_summary.csv"
    )

    with open(
        VALIDATION_DIR
        / "benchmark_summary.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
        )

    entity_validation.write_parquet(
        VALIDATION_DIR
        / "entity_validation.parquet"
    )

    source_validation.write_csv(
        VALIDATION_DIR
        / "source_validation.csv"
    )

    paid_validation.write_csv(
        VALIDATION_DIR
        / "paid_kpi_validation.csv"
    )

    validation_summary_frame(
        summary
    ).write_csv(
        VALIDATION_DIR
        / "benchmark_summary.csv"
    )

    print(
        "Internal reconciliation validation"
    )

    print()

    print(
        "=== OVERALL BENCHMARK ==="
    )

    for key, value in (
        summary.items()
    ):
        if isinstance(
            value,
            float,
        ):
            print(
                f"{key}: {value:.6f}"
            )
        else:
            print(
                f"{key}: {value:,}"
            )

    print()

    print(
        "=== SOURCE VALIDATION ==="
    )

    print(
        source_validation
    )

    print()

    print(
        "=== PAID KPI VALIDATION ==="
    )

    print(
        paid_validation
    )


if __name__ == "__main__":
    main()
