from __future__ import annotations

from pathlib import Path

import polars as pl

from .evaluate import evaluate_matches
from .resolve import (
    build_manual_review_queue,
    resolve_matches,
)


DATA_DIR = Path(
    "data/synthetic/crm"
)

TRUTH_DIR = (
    DATA_DIR
    / "ground_truth"
)

OUTPUT_DIR = Path(
    "data/processed/reconciliation"
)


def main() -> None:
    exact_matches = pl.read_parquet(
        OUTPUT_DIR
        / "exact_matches.parquet"
    )

    fuzzy_candidates = (
        pl.read_parquet(
            OUTPUT_DIR
            / "fuzzy_candidates.parquet"
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

    resolved = resolve_matches(
        exact_matches,
        fuzzy_candidates,
    )

    review_queue = (
        build_manual_review_queue(
            fuzzy_candidates
        )
    )

    resolved.write_parquet(
        OUTPUT_DIR
        / "reconciliation_results.parquet"
    )

    review_queue.write_csv(
        OUTPUT_DIR
        / "manual_review_queue.csv"
    )

    # --------------------------------------------------------
    # Evaluate all automatically accepted matches
    # --------------------------------------------------------

    auto_matches = resolved.filter(
        pl.col("review_status")
        == "auto_match"
    )

    (
        auto_metrics,
        auto_evaluated,
    ) = evaluate_matches(
        auto_matches,
        crm_map,
        marketing_map,
    )

    # --------------------------------------------------------
    # Evaluate review queue separately
    # --------------------------------------------------------

    (
        review_metrics,
        review_evaluated,
    ) = evaluate_matches(
        resolved.filter(
            pl.col("review_status")
            == "manual_review"
        ),
        crm_map,
        marketing_map,
    )

    # --------------------------------------------------------
    # Method-level benchmark
    # --------------------------------------------------------

    _, all_evaluated = (
        evaluate_matches(
            resolved,
            crm_map,
            marketing_map,
        )
    )

    method_summary = (
        all_evaluated
        .group_by(
            "match_method",
            "review_status",
        )
        .agg(
            pl.len()
            .alias("candidate_pairs"),

            pl.col(
                "is_true_match"
            )
            .sum()
            .alias("true_pairs"),
        )
        .with_columns(
            (
                pl.col("candidate_pairs")
                - pl.col("true_pairs")
            )
            .alias("false_pairs"),

            (
                pl.col("true_pairs")
                / pl.col("candidate_pairs")
            )
            .alias("precision"),
        )
        .sort(
            [
                "match_method",
                "review_status",
            ]
        )
    )

    print(
        "Final reconciliation resolution"
    )

    print()

    print("=== RESOLUTION COUNTS ===")

    print(
        resolved
        .group_by(
            "match_method",
            "review_status",
        )
        .len()
        .sort(
            [
                "match_method",
                "review_status",
            ]
        )
    )

    print()

    print("=== METHOD QUALITY ===")

    print(
        method_summary
    )

    print()

    print("=== AUTO-MATCH QUALITY ===")

    for key, value in (
        auto_metrics.items()
    ):
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

    print()

    print("=== MANUAL REVIEW QUEUE ===")

    print(
        "candidates:",
        f"{review_queue.height:,}",
    )

    print(
        "true candidates:",
        f"{int(review_evaluated['is_true_match'].sum()):,}",
    )

    print(
        "false candidates:",
        f"{review_queue.height - int(review_evaluated['is_true_match'].sum()):,}",
    )


if __name__ == "__main__":
    main()
