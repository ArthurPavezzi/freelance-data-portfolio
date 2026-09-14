from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from .report import (
    build_reconciliation_report,
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

    crm = pl.read_csv(
        RAW_DIR
        / "crm_leads.csv",
        try_parse_dates=True,
    )

    marketing = pl.read_csv(
        RAW_DIR
        / "marketing_leads.csv",
        try_parse_dates=True,
    )

    spend = pl.read_csv(
        RAW_DIR
        / "marketing_spend.csv",
        try_parse_dates=True,
    )

    clusters = pl.read_parquet(
        PROCESSED_DIR
        / "reconciled_leads.parquet"
    )

    membership = pl.read_parquet(
        PROCESSED_DIR
        / "reconciled_record_membership.parquet"
    )

    resolved = pl.read_parquet(
        PROCESSED_DIR
        / "reconciliation_results.parquet"
    )

    (
        metrics,
        source_report,
        campaign_report,
        unresolved,
    ) = build_reconciliation_report(
        crm,
        marketing,
        spend,
        clusters,
        membership,
        resolved,
    )

    summary = pl.DataFrame(
        {
            "metric": list(
                metrics.keys()
            ),
            "value": list(
                metrics.values()
            ),
        }
    )

    summary.write_csv(
        REPORT_DIR
        / "reconciliation_summary.csv"
    )

    source_report.write_csv(
        REPORT_DIR
        / "source_reconciliation.csv"
    )

    campaign_report.write_csv(
        REPORT_DIR
        / "campaign_performance.csv"
    )

    unresolved.write_csv(
        REPORT_DIR
        / "unresolved_records.csv"
    )

    with open(
        REPORT_DIR
        / "reconciliation_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics,
            file,
            indent=2,
        )

    print(
        "Reconciliation KPI audit"
    )
    print()

    print(
        "=== OVERALL ==="
    )

    for key, value in (
        metrics.items()
    ):
        print(
            f"{key}: {value:,}"
        )

    print()

    print(
        "=== SOURCE RECONCILIATION ==="
    )

    print(
        source_report
    )

    print()

    print(
        "=== PAID CAMPAIGNS ==="
    )

    print(
        campaign_report
    )

    print()

    print(
        "=== UNRESOLVED ==="
    )

    print(
        unresolved
        .group_by("system")
        .len()
    )


if __name__ == "__main__":
    main()
