from __future__ import annotations

from pathlib import Path

import polars as pl

from .match import generate_exact_candidates
from .normalize import (
    prepare_crm,
    prepare_marketing,
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

    crm_clean = prepare_crm(crm)

    marketing_clean = prepare_marketing(marketing)

    matches = generate_exact_candidates(
        crm_clean,
        marketing_clean,
    )

    matches.write_parquet(OUTPUT_DIR / "exact_matches.parquet")

    print("Exact cross-system matching")

    print(f"Accepted exact pairs: {matches.height:,}")


if __name__ == "__main__":
    main()
