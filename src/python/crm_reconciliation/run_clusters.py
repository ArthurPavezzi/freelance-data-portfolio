from __future__ import annotations

from pathlib import Path

import polars as pl

from .cluster import (
    build_reconciliation_clusters,
)

OUTPUT_DIR = Path("data/processed/reconciliation")


def main() -> None:
    resolved = pl.read_parquet(OUTPUT_DIR / "reconciliation_results.parquet")

    (
        clusters,
        membership,
    ) = build_reconciliation_clusters(resolved)

    clusters.write_parquet(OUTPUT_DIR / "reconciled_leads.parquet")

    membership.write_parquet(OUTPUT_DIR / "reconciled_record_membership.parquet")

    print("Reconciled lead entities")
    print()

    print(
        "Auto-match edges:",
        f"{resolved.filter(pl.col('review_status') == 'auto_match').height:,}",
    )

    print(
        "Reconciled lead entities:",
        f"{clusters.height:,}",
    )

    print(
        "CRM records represented:",
        f"{membership.filter(pl.col('system') == 'crm').height:,}",
    )

    print(
        "Marketing records represented:",
        f"{membership.filter(pl.col('system') == 'marketing').height:,}",
    )

    print()

    print("=== DUPLICATE STRUCTURE ===")

    print(
        clusters.select(
            pl.col("has_crm_duplicates").sum().alias("clusters_with_crm_duplicates"),
            pl.col("has_marketing_duplicates").sum().alias("clusters_with_marketing_duplicates"),
            pl.col("is_many_to_many").sum().alias("many_to_many_clusters"),
        )
    )

    print()

    print("=== CLUSTER SIZE DISTRIBUTION ===")

    print(
        clusters.group_by(
            "crm_record_count",
            "marketing_record_count",
        )
        .len()
        .sort(
            [
                "crm_record_count",
                "marketing_record_count",
            ]
        )
    )


if __name__ == "__main__":
    main()
