from __future__ import annotations

from pathlib import Path

import polars as pl

from .acquisition import (
    build_acquisition_source_summary,
    build_reconstructed_acquisition_universe,
    build_reconstructed_paid_kpis,
)

RAW_DIR = Path(
    "data/synthetic/crm/raw_exports"
)

PROCESSED_DIR = Path(
    "data/processed/reconciliation"
)

REPORT_DIR = Path(
    "reports/reconciliation"
)


def main() -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    triaged = pl.read_parquet(
        PROCESSED_DIR
        / "triaged_lead_ledger.parquet"
    )

    deduped = pl.read_parquet(
        PROCESSED_DIR
        / "deduped_singletons.parquet"
    )

    spend = pl.read_csv(
        RAW_DIR
        / "marketing_spend.csv",
        try_parse_dates=True,
    )

    universe = (
        build_reconstructed_acquisition_universe(
            triaged,
            deduped,
        )
    )

    source_summary = (
        build_acquisition_source_summary(
            universe
        )
    )

    paid_kpis = (
        build_reconstructed_paid_kpis(
            universe,
            spend,
        )
    )

    universe.write_parquet(
        PROCESSED_DIR
        / "reconstructed_acquisition_universe.parquet"
    )

    universe.write_csv(
        PROCESSED_DIR
        / "reconstructed_acquisition_universe.csv"
    )

    source_summary.write_csv(
        REPORT_DIR
        / "reconstructed_sources.csv"
    )

    paid_kpis.write_csv(
        REPORT_DIR
        / "reconstructed_paid_kpis.csv"
    )

    print(
        "Reconstructed acquisition universe"
    )
    print()

    print(
        "Acquisition entities:",
        f"{universe.height:,}",
    )

    print()

    print(
        "=== STATUS ==="
    )

    print(
        universe
        .group_by(
            "acquisition_status"
        )
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print()

    print(
        "=== SOURCE COMPOSITION ==="
    )

    print(
        source_summary
    )

    print()

    print(
        "=== PAID KPI AUDIT ==="
    )

    print(
        paid_kpis
    )


if __name__ == "__main__":
    main()
