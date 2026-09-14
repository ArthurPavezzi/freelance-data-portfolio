from __future__ import annotations

import polars as pl

AUTO_MATCH_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.75
MIN_EVIDENCE_COUNT = 2


RESULT_COLUMNS = [
    "crm_record_id",
    "marketing_record_id",
    "match_method",
    "match_rule",
    "match_score",
    "review_status",
    "time_delta_minutes",
    "name_similarity",
    "email_similarity",
    "phone_similarity",
    "zip_similarity",
    "identity_score",
    "time_score",
    "evidence_count",
    "evidence_weight",
]


def resolve_matches(
    exact_matches: pl.DataFrame,
    fuzzy_candidates: pl.DataFrame,
) -> pl.DataFrame:
    """
    Combine deterministic and fuzzy cross-system links.

    Exact matches are always accepted automatically.

    Fuzzy candidates:
        score >= 0.90 -> auto-match
        0.75 <= score < 0.90 -> manual review
        score < 0.75 -> rejected and omitted from resolved output

    Ground-truth identifiers are never used here.
    """
    exact = (
        exact_matches.select(
            "crm_record_id",
            "marketing_record_id",
            "time_delta_minutes",
            "match_rule",
            "match_score",
        )
        .with_columns(
            pl.lit("exact").alias("match_method"),
            pl.lit("auto_match").alias("review_status"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("name_similarity"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("email_similarity"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("phone_similarity"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("zip_similarity"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("identity_score"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("time_score"),
            pl.lit(
                None,
                dtype=pl.Int64,
            ).alias("evidence_count"),
            pl.lit(
                None,
                dtype=pl.Float64,
            ).alias("evidence_weight"),
        )
        .select(RESULT_COLUMNS)
    )

    fuzzy = (
        fuzzy_candidates.filter(
            (pl.col("fuzzy_score") >= REVIEW_THRESHOLD)
            & (pl.col("evidence_count") >= MIN_EVIDENCE_COUNT)
        )
        .with_columns(
            pl.lit("fuzzy").alias("match_method"),
            pl.lit("fuzzy_identity").alias("match_rule"),
            pl.col("fuzzy_score").alias("match_score"),
            pl.when(pl.col("fuzzy_score") >= AUTO_MATCH_THRESHOLD)
            .then(pl.lit("auto_match"))
            .otherwise(pl.lit("manual_review"))
            .alias("review_status"),
        )
        .select(RESULT_COLUMNS)
    )

    resolved = pl.concat(
        [
            exact,
            fuzzy,
        ],
        how="vertical",
    )

    return resolved.sort(
        [
            "review_status",
            "match_score",
        ],
        descending=[
            False,
            True,
        ],
    )


def build_manual_review_queue(
    fuzzy_candidates: pl.DataFrame,
) -> pl.DataFrame:
    """
    Produce a human-readable queue containing only ambiguous
    fuzzy candidates requiring manual review.
    """
    return (
        fuzzy_candidates.filter(
            (pl.col("fuzzy_score") >= REVIEW_THRESHOLD)
            & (pl.col("fuzzy_score") < AUTO_MATCH_THRESHOLD)
            & (pl.col("evidence_count") >= MIN_EVIDENCE_COUNT)
        )
        .select(
            "crm_record_id",
            "marketing_record_id",
            "created_at",
            "captured_at",
            "time_delta_minutes",
            "crm_name",
            "marketing_name",
            "name_similarity",
            "crm_email",
            "marketing_email",
            "email_similarity",
            "crm_phone",
            "marketing_phone",
            "phone_similarity",
            "crm_zip",
            "marketing_zip",
            "zip_similarity",
            "service",
            "identity_score",
            "time_score",
            "evidence_count",
            "evidence_weight",
            "fuzzy_score",
        )
        .sort(
            "fuzzy_score",
            descending=True,
        )
    )
