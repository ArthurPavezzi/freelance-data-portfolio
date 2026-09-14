from __future__ import annotations

import polars as pl

from .report import (
    CRM_SOURCE_MAP,
    MARKETING_SOURCE_MAP,
    TRACKABLE_SOURCES,
)

LEDGER_COLUMNS = [
    "ledger_id",
    "ledger_status",
    "event_timestamp",
    "source_canonical",
    "campaign",
    "service",
    "crm_record_count",
    "marketing_record_count",
    "primary_crm_record_id",
    "primary_marketing_record_id",
    "match_method",
    "needs_review",
    "review_candidate_count",
    "in_marketing_scope",
    "source_disagreement",
    "service_disagreement",
]


def _prepare_crm(
    crm: pl.DataFrame,
) -> pl.DataFrame:
    return crm.with_columns(
        pl.col("source")
        .map_elements(
            lambda value: (
                None
                if value is None
                else CRM_SOURCE_MAP.get(
                    value,
                    value,
                )
            ),
            return_dtype=pl.String,
        )
        .alias("source_canonical")
    )


def _prepare_marketing(
    marketing: pl.DataFrame,
) -> pl.DataFrame:
    return marketing.with_columns(
        pl.col("source_label")
        .map_elements(
            lambda value: (
                None
                if value is None
                else MARKETING_SOURCE_MAP.get(
                    value,
                    value,
                )
            ),
            return_dtype=pl.String,
        )
        .alias("source_canonical")
    )


def build_unified_ledger(
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
    clusters: pl.DataFrame,
    membership: pl.DataFrame,
    resolved: pl.DataFrame,
) -> pl.DataFrame:
    """
    Build a unified operational lead ledger.

    Cross-system auto-matched components are represented as reconciled
    lead entities.

    Records not belonging to a confirmed component remain singleton
    unresolved observations.

    Hidden ground-truth identifiers are never used.
    """
    crm = _prepare_crm(
        crm
    )

    marketing = _prepare_marketing(
        marketing
    )

    # --------------------------------------------------------
    # Membership
    # --------------------------------------------------------

    crm_members = (
        membership
        .filter(
            pl.col("system")
            == "crm"
        )
        .rename(
            {
                "record_id": (
                    "crm_record_id"
                )
            }
        )
    )

    marketing_members = (
        membership
        .filter(
            pl.col("system")
            == "marketing"
        )
        .rename(
            {
                "record_id": (
                    "marketing_record_id"
                )
            }
        )
    )

    # --------------------------------------------------------
    # CRM-side representation of confirmed clusters
    # --------------------------------------------------------

    crm_cluster = (
        crm_members
        .join(
            crm,
            on="crm_record_id",
            how="left",
        )
        .group_by(
            "reconciled_lead_id"
        )
        .agg(
            pl.col(
                "crm_record_id"
            )
            .sort()
            .first()
            .alias(
                "primary_crm_record_id"
            ),

            pl.len()
            .alias(
                "observed_crm_count"
            ),

            pl.col("created_at")
            .min()
            .alias(
                "crm_timestamp"
            ),

            pl.col(
                "source_canonical"
            )
            .drop_nulls()
            .first()
            .alias(
                "crm_source"
            ),

            pl.col("campaign")
            .drop_nulls()
            .first()
            .alias(
                "crm_campaign"
            ),

            pl.col("service")
            .drop_nulls()
            .first()
            .alias(
                "crm_service"
            ),
        )
    )

    # --------------------------------------------------------
    # Marketing-side representation of confirmed clusters
    # --------------------------------------------------------

    marketing_cluster = (
        marketing_members
        .join(
            marketing,
            on="marketing_record_id",
            how="left",
        )
        .group_by(
            "reconciled_lead_id"
        )
        .agg(
            pl.col(
                "marketing_record_id"
            )
            .sort()
            .first()
            .alias(
                "primary_marketing_record_id"
            ),

            pl.len()
            .alias(
                "observed_marketing_count"
            ),

            pl.col("captured_at")
            .min()
            .alias(
                "marketing_timestamp"
            ),

            pl.col(
                "source_canonical"
            )
            .drop_nulls()
            .first()
            .alias(
                "marketing_source"
            ),

            pl.col("campaign")
            .drop_nulls()
            .first()
            .alias(
                "marketing_campaign"
            ),

            pl.col("service")
            .drop_nulls()
            .first()
            .alias(
                "marketing_service"
            ),
        )
    )

    # --------------------------------------------------------
    # Confirmed cross-system entities
    # --------------------------------------------------------

    confirmed = (
        clusters
        .join(
            crm_cluster,
            on="reconciled_lead_id",
            how="left",
        )
        .join(
            marketing_cluster,
            on="reconciled_lead_id",
            how="left",
        )
        .with_columns(
            pl.col(
                "reconciled_lead_id"
            )
            .alias("ledger_id"),

            pl.lit(
                "cross_system_confirmed"
            )
            .alias(
                "ledger_status"
            ),

            pl.coalesce(
                [
                    pl.col(
                        "marketing_timestamp"
                    ),
                    pl.col(
                        "crm_timestamp"
                    ),
                ]
            )
            .alias(
                "event_timestamp"
            ),

            # Prefer marketing attribution for acquisition source.
            pl.coalesce(
                [
                    pl.col(
                        "marketing_source"
                    ),
                    pl.col(
                        "crm_source"
                    ),
                ]
            )
            .alias(
                "source_canonical"
            ),

            pl.coalesce(
                [
                    pl.col(
                        "marketing_campaign"
                    ),
                    pl.col(
                        "crm_campaign"
                    ),
                ]
            )
            .alias(
                "campaign"
            ),

            pl.coalesce(
                [
                    pl.col(
                        "marketing_service"
                    ),
                    pl.col(
                        "crm_service"
                    ),
                ]
            )
            .alias(
                "service"
            ),

            pl.col(
                "crm_record_count"
            )
            .cast(
                pl.Int64
            ),

            pl.col(
                "marketing_record_count"
            )
            .cast(
                pl.Int64
            ),

            pl.when(
                pl.col(
                    "fuzzy_edge_count"
                )
                > 0
            )
            .then(
                pl.lit(
                    "exact_and_or_fuzzy"
                )
            )
            .otherwise(
                pl.lit("exact")
            )
            .alias(
                "match_method"
            ),

            pl.lit(False)
            .alias(
                "needs_review"
            ),

            pl.lit(
                0,
                dtype=pl.Int64,
            )
            .alias(
                "review_candidate_count"
            ),

            pl.lit(True)
            .alias(
                "in_marketing_scope"
            ),

            (
                pl.col(
                    "crm_source"
                )
                .is_not_null()
                & pl.col(
                    "marketing_source"
                )
                .is_not_null()
                & (
                    pl.col(
                        "crm_source"
                    )
                    != pl.col(
                        "marketing_source"
                    )
                )
            )
            .alias(
                "source_disagreement"
            ),

            (
                pl.col(
                    "crm_service"
                )
                .is_not_null()
                & pl.col(
                    "marketing_service"
                )
                .is_not_null()
                & (
                    pl.col(
                        "crm_service"
                    )
                    != pl.col(
                        "marketing_service"
                    )
                )
            )
            .alias(
                "service_disagreement"
            ),
        )
        .select(
            LEDGER_COLUMNS
        )
    )

    # --------------------------------------------------------
    # Manual-review participation
    # --------------------------------------------------------

    review = resolved.filter(
        pl.col("review_status")
        == "manual_review"
    )

    crm_review = (
        review
        .group_by(
            "crm_record_id"
        )
        .len()
        .rename(
            {
                "len": (
                    "review_candidate_count"
                )
            }
        )
    )

    marketing_review = (
        review
        .group_by(
            "marketing_record_id"
        )
        .len()
        .rename(
            {
                "len": (
                    "review_candidate_count"
                )
            }
        )
    )

    # --------------------------------------------------------
    # CRM-only observations
    # --------------------------------------------------------

    crm_only = (
        crm
        .join(
            crm_members.select(
                "crm_record_id"
            ),
            on="crm_record_id",
            how="anti",
        )
        .join(
            crm_review,
            on="crm_record_id",
            how="left",
        )
        .with_columns(
            pl.col(
                "review_candidate_count"
            )
            .fill_null(0)
            .cast(pl.Int64),

            (
                pl.col(
                    "source_canonical"
                )
                .is_in(
                    TRACKABLE_SOURCES
                )
                | pl.col(
                    "source_canonical"
                )
                .is_null()
            )
            .alias(
                "in_marketing_scope"
            ),
        )
        .with_columns(
            (
                pl.lit("CRMONLY:")
                + pl.col(
                    "crm_record_id"
                )
            )
            .alias("ledger_id"),

            pl.when(
                pl.col(
                    "review_candidate_count"
                )
                > 0
            )
            .then(
                pl.lit(
                    "manual_review_pending"
                )
            )
            .otherwise(
                pl.lit(
                    "crm_only"
                )
            )
            .alias(
                "ledger_status"
            ),

            pl.col("created_at")
            .alias(
                "event_timestamp"
            ),

            pl.lit(
                1,
                dtype=pl.Int64,
            )
            .alias(
                "crm_record_count"
            ),

            pl.lit(
                0,
                dtype=pl.Int64,
            )
            .alias(
                "marketing_record_count"
            ),

            pl.col(
                "crm_record_id"
            )
            .alias(
                "primary_crm_record_id"
            ),

            pl.lit(
                None,
                dtype=pl.String,
            )
            .alias(
                "primary_marketing_record_id"
            ),

            pl.lit(
                None,
                dtype=pl.String,
            )
            .alias(
                "match_method"
            ),

            (
                pl.col(
                    "review_candidate_count"
                )
                > 0
            )
            .alias(
                "needs_review"
            ),

            pl.lit(False)
            .alias(
                "source_disagreement"
            ),

            pl.lit(False)
            .alias(
                "service_disagreement"
            ),
        )
        .select(
            LEDGER_COLUMNS
        )
    )

    # --------------------------------------------------------
    # Marketing-only observations
    # --------------------------------------------------------

    marketing_only = (
        marketing
        .join(
            marketing_members.select(
                "marketing_record_id"
            ),
            on="marketing_record_id",
            how="anti",
        )
        .join(
            marketing_review,
            on="marketing_record_id",
            how="left",
        )
        .with_columns(
            pl.col(
                "review_candidate_count"
            )
            .fill_null(0)
            .cast(pl.Int64)
        )
        .with_columns(
            (
                pl.lit("MKTONLY:")
                + pl.col(
                    "marketing_record_id"
                )
            )
            .alias("ledger_id"),

            pl.when(
                pl.col(
                    "review_candidate_count"
                )
                > 0
            )
            .then(
                pl.lit(
                    "manual_review_pending"
                )
            )
            .otherwise(
                pl.lit(
                    "marketing_only"
                )
            )
            .alias(
                "ledger_status"
            ),

            pl.col("captured_at")
            .alias(
                "event_timestamp"
            ),

            pl.lit(
                0,
                dtype=pl.Int64,
            )
            .alias(
                "crm_record_count"
            ),

            pl.lit(
                1,
                dtype=pl.Int64,
            )
            .alias(
                "marketing_record_count"
            ),

            pl.lit(
                None,
                dtype=pl.String,
            )
            .alias(
                "primary_crm_record_id"
            ),

            pl.col(
                "marketing_record_id"
            )
            .alias(
                "primary_marketing_record_id"
            ),

            pl.lit(
                None,
                dtype=pl.String,
            )
            .alias(
                "match_method"
            ),

            (
                pl.col(
                    "review_candidate_count"
                )
                > 0
            )
            .alias(
                "needs_review"
            ),

            pl.lit(True)
            .alias(
                "in_marketing_scope"
            ),

            pl.lit(False)
            .alias(
                "source_disagreement"
            ),

            pl.lit(False)
            .alias(
                "service_disagreement"
            ),
        )
        .select(
            LEDGER_COLUMNS
        )
    )

    return (
        pl.concat(
            [
                confirmed,
                crm_only,
                marketing_only,
            ],
            how="vertical",
        )
        .sort(
            [
                "event_timestamp",
                "ledger_id",
            ]
        )
    )
