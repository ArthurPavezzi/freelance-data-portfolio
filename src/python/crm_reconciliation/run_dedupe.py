from __future__ import annotations

from pathlib import Path

import polars as pl

from .dedupe import (
    deduplicate_singletons,
)

RAW_DIR = Path(
    "data/synthetic/crm/raw_exports"
)

PROCESSED_DIR = Path(
    "data/processed/reconciliation"
)


def main() -> None:
    triaged = pl.read_parquet(
        PROCESSED_DIR
        / "triaged_lead_ledger.parquet"
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

    (
        entities,
        membership,
    ) = deduplicate_singletons(
        triaged,
        crm,
        marketing,
    )

    entities.write_parquet(
        PROCESSED_DIR
        / "deduped_singletons.parquet"
    )

    membership.write_parquet(
        PROCESSED_DIR
        / "deduped_singleton_membership.parquet"
    )

    print(
        "Within-system singleton deduplication"
    )
    print()

    print(
        "=== BY SYSTEM ==="
    )

    print(
        entities
        .group_by("system")
        .agg(
            pl.len()
            .alias("entities"),

            pl.col(
                "record_count"
            )
            .sum()
            .alias(
                "source_records"
            ),

            (
                pl.col(
                    "record_count"
                )
                - 1
            )
            .sum()
            .alias(
                "duplicate_records_collapsed"
            ),
        )
    )

    print()

    print(
        "=== ENTITY SIZE ==="
    )

    print(
        entities
        .group_by(
            "system",
            "record_count",
        )
        .len()
        .sort(
            [
                "system",
                "record_count",
            ]
        )
    )

    print()

    print(
        "=== BY TRIAGE STATUS ==="
    )

    print(
        entities
        .group_by(
            "system",
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
