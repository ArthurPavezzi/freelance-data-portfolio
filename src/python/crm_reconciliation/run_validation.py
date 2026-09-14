from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from .evaluate import (
    evaluate_matches,
)
from .validation import (
    build_internal_validation,
    validation_summary_frame,
)

RAW_DIR = Path("data/synthetic/crm/raw_exports")

TRUTH_DIR = Path("data/synthetic/crm/ground_truth")

PROCESSED_DIR = Path("data/processed/reconciliation")

VALIDATION_DIR = Path("reports/reconciliation/internal_validation")


def main() -> None:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True, )

    universe = pl.read_parquet(PROCESSED_DIR / "reconstructed_acquisition_universe.parquet")

    confirmed_membership = (
        pl.read_parquet(PROCESSED_DIR / "reconciled_record_membership.parquet")
    )

    singleton_membership = (
        pl.read_parquet(PROCESSED_DIR / "deduped_singleton_membership.parquet")
    )

    crm_map = pl.read_parquet(TRUTH_DIR / "crm_observation_map.parquet")

    marketing_map = pl.read_parquet(TRUTH_DIR / "marketing_observation_map.parquet")

    leads = pl.read_parquet(TRUTH_DIR / "leads.parquet")

    spend = pl.read_csv(RAW_DIR / "marketing_spend.csv", try_parse_dates=True, )

    exact_matches = pl.read_parquet(PROCESSED_DIR / "exact_matches.parquet")
    
    resolved_matches = pl.read_parquet(PROCESSED_DIR / "reconciliation_results.parquet")

    (
        exact_metrics,
        exact_evaluated,
    ) = evaluate_matches(
        exact_matches,
        crm_map,
        marketing_map,
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

    auto_matches = (resolved_matches.filter(pl.col("review_status") == "auto_match"))
    
    review_matches = (resolved_matches.filter(pl.col("review_status") == "manual_review"))
    
    (
        auto_metrics,
        auto_evaluated,
    ) = evaluate_matches(
        auto_matches,
        crm_map,
        marketing_map,
    )
    
    (
        review_metrics,
        review_evaluated,
    ) = evaluate_matches(
        review_matches,
        crm_map,
        marketing_map,
    )

    _, resolved_evaluated = (
        evaluate_matches(
            resolved_matches,
            crm_map,
            marketing_map,
        )
    )

    matching_summary = pl.DataFrame(
        {
            "stage": [
                "exact_baseline",
                "final_auto_matches",
                "manual_review_queue",
            ],
            "candidate_pairs": [
                exact_metrics[
                    "pair_predicted"
                ],
                auto_metrics[
                    "pair_predicted"
                ],
                review_metrics[
                    "pair_predicted"
                ],
            ],
            "pair_precision": [
                exact_metrics[
                    "pair_precision"
                ],
                auto_metrics[
                    "pair_precision"
                ],
                review_metrics[
                    "pair_precision"
                ],
            ],
            "pair_recall": [
                exact_metrics[
                    "pair_recall"
                ],
                auto_metrics[
                    "pair_recall"
                ],
                review_metrics[
                    "pair_recall"
                ],
            ],
            "lead_recall": [
                exact_metrics[
                    "lead_recall"
                ],
                auto_metrics[
                    "lead_recall"
                ],
                review_metrics[
                    "lead_recall"
                ],
            ],
        }
    )
    
    matching_summary.write_csv(VALIDATION_DIR / "matching_stage_validation.csv")

    method_summary = (
        resolved_evaluated
        .group_by(
            "match_method",
            "review_status",
        )
        .agg(
            pl.len()
            .alias(
                "candidate_pairs"
            ),
    
            pl.col(
                "is_true_match"
            )
            .sum()
            .alias(
                "true_pairs"
            ),
        )
        .with_columns(
            (
                pl.col(
                    "candidate_pairs"
                )
                - pl.col(
                    "true_pairs"
                )
            )
            .alias(
                "false_pairs"
            ),
    
            (
                pl.col(
                    "true_pairs"
                )
                / pl.col(
                    "candidate_pairs"
                )
            )
            .alias(
                "precision"
            ),
        )
        .sort(
            [
                "match_method",
                "review_status",
            ]
        )
    )

    exact_evaluated.write_parquet(
        VALIDATION_DIR
        / "exact_matches_evaluated.parquet"
    )
    
    resolved_evaluated.write_parquet(
        VALIDATION_DIR / "resolved_matches_evaluated.parquet"
    )
    
    method_summary.write_csv(VALIDATION_DIR / "match_method_validation.csv")

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
        "=== EXACT-MATCH BENCHMARK ==="
    )
    
    for key, value in (
        exact_metrics.items()
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
    
    print(
        "=== RESOLUTION METHOD QUALITY ==="
    )
    
    print(
        method_summary
    )
    
    print()
    
    print(
        "=== AUTO-MATCH BENCHMARK ==="
    )
    
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
    
    print(
        "=== MANUAL-REVIEW BENCHMARK ==="
    )
    
    for key, value in (
        review_metrics.items()
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
