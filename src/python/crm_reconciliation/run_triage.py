from __future__ import annotations

from pathlib import Path

import polars as pl

from .triage import triage_ledger

RAW_DIR = Path("data/synthetic/crm/raw_exports")

PROCESSED_DIR = Path("data/processed/reconciliation")


def main() -> None:
    ledger = pl.read_parquet(PROCESSED_DIR / "unified_lead_ledger.parquet")

    crm = pl.read_csv(
        RAW_DIR / "crm_leads.csv",
        try_parse_dates=True,
    )

    marketing = pl.read_csv(
        RAW_DIR / "marketing_leads.csv",
        try_parse_dates=True,
    )

    triaged = triage_ledger(
        ledger,
        crm,
        marketing,
    )

    triaged.write_parquet(PROCESSED_DIR / "triaged_lead_ledger.parquet")

    triaged.write_csv(PROCESSED_DIR / "triaged_lead_ledger.csv")

    print("Lead ledger triage")
    print()

    print("=== TRIAGE STATUS ===")

    print(
        triaged.group_by("triage_status")
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print()

    print("=== RECOMMENDED ACTION ===")

    print(
        triaged.group_by("recommended_action")
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print()

    print("=== MARKETING-ONLY ===")

    print(
        triaged.filter(pl.col("ledger_status") == "marketing_only")
        .group_by(
            "triage_status",
            "source_canonical",
        )
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print()

    print("=== CRM-ONLY IN SCOPE ===")

    print(
        triaged.filter(
            pl.col("triage_status").is_in(
                [
                    "crm_only_trackable",
                    "crm_only_unknown_source",
                ]
            )
        )
        .group_by(
            "triage_status",
            "source_canonical",
        )
        .len()
        .sort(
            "len",
            descending=True,
        )
    )


if __name__ == "__main__":
    main()
