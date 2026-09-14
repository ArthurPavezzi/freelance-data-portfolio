from __future__ import annotations

from pathlib import Path

import polars as pl

from .ledger import (
    build_unified_ledger,
)

RAW_DIR = Path("data/synthetic/crm/raw_exports")

PROCESSED_DIR = Path("data/processed/reconciliation")


def main() -> None:
    crm = pl.read_csv(
        RAW_DIR / "crm_leads.csv",
        try_parse_dates=True,
    )

    marketing = pl.read_csv(
        RAW_DIR / "marketing_leads.csv",
        try_parse_dates=True,
    )

    clusters = pl.read_parquet(PROCESSED_DIR / "reconciled_leads.parquet")

    membership = pl.read_parquet(PROCESSED_DIR / "reconciled_record_membership.parquet")

    resolved = pl.read_parquet(PROCESSED_DIR / "reconciliation_results.parquet")

    ledger = build_unified_ledger(
        crm,
        marketing,
        clusters,
        membership,
        resolved,
    )

    ledger.write_parquet(PROCESSED_DIR / "unified_lead_ledger.parquet")

    ledger.write_csv(PROCESSED_DIR / "unified_lead_ledger.csv")

    print("Unified lead ledger")
    print()

    print(
        "Ledger rows:",
        f"{ledger.height:,}",
    )

    print()

    print("=== STATUS ===")

    print(
        ledger.group_by("ledger_status")
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print()

    print("=== MARKETING SCOPE ===")

    print(
        ledger.group_by(
            "ledger_status",
            "in_marketing_scope",
        )
        .len()
        .sort(
            [
                "ledger_status",
                "in_marketing_scope",
            ]
        )
    )

    print()

    print("=== DATA DISAGREEMENTS ===")

    print(
        ledger.filter(pl.col("ledger_status") == "cross_system_confirmed").select(
            pl.col("source_disagreement").sum().alias("source_disagreements"),
            pl.col("service_disagreement").sum().alias("service_disagreements"),
        )
    )

    print()

    print("=== REVIEW ===")

    print(
        ledger.filter(pl.col("needs_review")).select(
            pl.len().alias("records_pending_review"),
            pl.col("review_candidate_count").sum().alias("candidate_links"),
        )
    )


if __name__ == "__main__":
    main()
