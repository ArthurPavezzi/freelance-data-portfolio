from __future__ import annotations

from typing import Any

import polars as pl

TRACKABLE_SOURCES = [
    "Google Ads",
    "Facebook Ads",
    "Organic Search",
    "Direct",
]


CRM_SOURCE_MAP = {
    "Google Ads": "Google Ads",
    "Google": "Google Ads",
    "Google PPC": "Google Ads",
    "GAds": "Google Ads",
    "Paid Search": "Google Ads",

    "Facebook Ads": "Facebook Ads",
    "Facebook": "Facebook Ads",
    "Meta Ads": "Facebook Ads",
    "FB Ads": "Facebook Ads",
    "Paid Social": "Facebook Ads",

    "Organic Search": "Organic Search",
    "Organic": "Organic Search",
    "SEO": "Organic Search",
    "Google Organic": "Organic Search",

    "Direct": "Direct",
    "Website Direct": "Direct",
    "Call In": "Direct",

    "Referral": "Referral",
    "Customer Referral": "Referral",
    "Ref": "Referral",

    "Partner": "Partner",
    "Partner Referral": "Partner",
    "Strategic Partner": "Partner",
}


MARKETING_SOURCE_MAP = {
    "google_paid": "Google Ads",
    "meta_paid": "Facebook Ads",
    "organic_search": "Organic Search",
    "direct_website": "Direct",
}


def canonicalize_crm_source(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    return CRM_SOURCE_MAP.get(
        value,
        value,
    )


def canonicalize_marketing_source(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    return MARKETING_SOURCE_MAP.get(
        value,
        value,
    )


def _prepare_crm(
    crm: pl.DataFrame,
) -> pl.DataFrame:
    return crm.with_columns(
        pl.col("source")
        .map_elements(
            canonicalize_crm_source,
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
            canonicalize_marketing_source,
            return_dtype=pl.String,
        )
        .alias("source_canonical")
    )


def _build_cluster_attribution(
    marketing: pl.DataFrame,
    membership: pl.DataFrame,
) -> pl.DataFrame:
    """
    Assign a canonical source and campaign to each reconciled lead
    using observable marketing-system records.

    Duplicate marketing observations do not increase lead counts.
    """
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

    attributed = (
        marketing_members
        .join(
            marketing.select(
                "marketing_record_id",
                "source_canonical",
                "campaign",
            ),
            on="marketing_record_id",
            how="left",
        )
        .group_by(
            "reconciled_lead_id"
        )
        .agg(
            pl.col(
                "source_canonical"
            )
            .drop_nulls()
            .first()
            .alias(
                "source_canonical"
            ),

            pl.col(
                "source_canonical"
            )
            .drop_nulls()
            .n_unique()
            .alias(
                "source_count"
            ),

            pl.col("campaign")
            .drop_nulls()
            .first()
            .alias("campaign"),

            pl.col("campaign")
            .drop_nulls()
            .n_unique()
            .alias(
                "campaign_count"
            ),
        )
    )

    return attributed


def build_reconciliation_report(
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
    spend: pl.DataFrame,
    clusters: pl.DataFrame,
    membership: pl.DataFrame,
    resolved: pl.DataFrame,
) -> tuple[
    dict[str, Any],
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Build client-facing reconciliation and KPI audit outputs.

    No hidden ground-truth IDs or evaluation tables are used.
    """
    crm = _prepare_crm(
        crm
    )

    marketing = (
        _prepare_marketing(
            marketing
        )
    )

    cluster_attribution = (
        _build_cluster_attribution(
            marketing,
            membership,
        )
    )

    # --------------------------------------------------------
    # Basic membership tables
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
    # Overall metrics
    # --------------------------------------------------------

    auto_matches = (
        resolved
        .filter(
            pl.col("review_status")
            == "auto_match"
        )
    )

    manual_review = (
        resolved
        .filter(
            pl.col("review_status")
            == "manual_review"
        )
    )

    unlinked_crm_all = (
        crm
        .join(
            crm_members.select(
                "crm_record_id"
            ),
            on="crm_record_id",
            how="anti",
        )
    )
    
    unlinked_marketing_all = (
        marketing
        .join(
            marketing_members.select(
                "marketing_record_id"
            ),
            on="marketing_record_id",
            how="anti",
        )
    )
    
    unlinked_crm_in_scope = (
        unlinked_crm_all
        .filter(
            (
                pl.col(
                    "source_canonical"
                )
                .is_in(
                    TRACKABLE_SOURCES
                )
            )
            | (
                pl.col(
                    "source_canonical"
                )
                .is_null()
            )
        )
    )
    
    unlinked_crm_out_of_scope = (
        unlinked_crm_all
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_not_null()
            & ~pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
    )

    metrics = {
        "raw_crm_records": (
            crm.height
        ),
        "raw_marketing_records": (
            marketing.height
        ),
        "auto_match_edges": (
            auto_matches.height
        ),
        "exact_auto_match_edges": (
            auto_matches
            .filter(
                pl.col("match_method")
                == "exact"
            )
            .height
        ),
        "fuzzy_auto_match_edges": (
            auto_matches
            .filter(
                pl.col("match_method")
                == "fuzzy"
            )
            .height
        ),
        "manual_review_candidates": (
            manual_review.height
        ),
        "reconciled_leads": (
            clusters.height
        ),
        "crm_records_linked": (
            crm_members.height
        ),
        "marketing_records_linked": (
            marketing_members.height
        ),
        "clusters_with_crm_duplicates": int(
            clusters[
                "has_crm_duplicates"
            ].sum()
        ),
        "clusters_with_marketing_duplicates": int(
            clusters[
                "has_marketing_duplicates"
            ].sum()
        ),
        "many_to_many_clusters": int(
            clusters[
                "is_many_to_many"
            ].sum()
        ),
        "crm_records_unlinked_total": (
            unlinked_crm_all.height
        ),
        "crm_records_unlinked_in_scope_or_unknown": (
            unlinked_crm_in_scope.height
        ),
        "crm_records_unlinked_out_of_scope": (
            unlinked_crm_out_of_scope.height
        ),
        "marketing_records_unlinked_total": (
            unlinked_marketing_all.height
        ),
    }

    # --------------------------------------------------------
    # Raw record counts by source
    # --------------------------------------------------------

    raw_crm_by_source = (
        crm
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "raw_crm_records"
                )
            }
        )
    )

    raw_marketing_by_source = (
        marketing
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "raw_marketing_records"
                )
            }
        )
    )

    # --------------------------------------------------------
    # Linked record counts attributed by reconciled entity
    # --------------------------------------------------------

    linked_crm_by_source = (
        crm_members
        .join(
            crm.select(
                "crm_record_id",
                "source_canonical",
            ),
            on="crm_record_id",
            how="left",
        )
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "linked_crm_records"
                )
            }
        )
    )

    linked_marketing_by_source = (
        marketing_members
        .join(
            marketing.select(
                "marketing_record_id",
                "source_canonical",
            ),
            on="marketing_record_id",
            how="left",
        )
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "linked_marketing_records"
                )
            }
        )
    )

    reconciled_by_source = (
        cluster_attribution
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "reconciled_leads"
                )
            }
        )
    )

    crm_source_recovered = (
        crm_members
        .join(
            crm.select(
                "crm_record_id",
                pl.col(
                    "source_canonical"
                ).alias(
                    "crm_source"
                ),
            ),
            on="crm_record_id",
            how="left",
        )
        .join(
            cluster_attribution.select(
                "reconciled_lead_id",
                pl.col(
                    "source_canonical"
                ).alias(
                    "reconciled_source"
                ),
            ),
            on="reconciled_lead_id",
            how="left",
        )
        .filter(
            pl.col("crm_source").is_null()
            & pl.col(
                "reconciled_source"
            ).is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "reconciled_source"
        )
        .len()
        .rename(
            {
                "reconciled_source": (
                    "source_canonical"
                ),
                "len": (
                    "crm_missing_source_recovered"
                ),
            }
        )
    )

    # --------------------------------------------------------
    # Paid-media reporting
    # --------------------------------------------------------

    spend_by_source = (
        spend
        .group_by("source")
        .agg(
            pl.col("spend")
            .sum()
            .alias("spend"),

            pl.col(
                "platform_conversions"
            )
            .sum()
            .alias(
                "platform_conversions"
            ),

            pl.col("clicks")
            .sum()
            .alias("clicks"),

            pl.col("impressions")
            .sum()
            .alias("impressions"),
        )
        .rename(
            {
                "source": (
                    "source_canonical"
                )
            }
        )
    )

    sources = pl.DataFrame(
        {
            "source_canonical": (
                TRACKABLE_SOURCES
            )
        }
    )

    source_report = (
        sources
        .join(
            raw_crm_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            raw_marketing_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            linked_crm_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            linked_marketing_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            reconciled_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            spend_by_source,
            on="source_canonical",
            how="left",
        )
        .with_columns(
            pl.col(
                "raw_crm_records"
            )
            .fill_null(0),

            pl.col(
                "raw_marketing_records"
            )
            .fill_null(0),

            pl.col(
                "linked_crm_records"
            )
            .fill_null(0),

            pl.col(
                "linked_marketing_records"
            )
            .fill_null(0),

            pl.col(
                "reconciled_leads"
            )
            .fill_null(0),
        )
        .with_columns(
            (
                pl.col(
                    "raw_crm_records"
                )
                - pl.col(
                    "linked_crm_records"
                )
            )
            .alias(
                "unlinked_crm_records"
            ),

            (
                pl.col(
                    "raw_marketing_records"
                )
                - pl.col(
                    "linked_marketing_records"
                )
            )
            .alias(
                "unlinked_marketing_records"
            ),

            pl.when(
                pl.col(
                    "platform_conversions"
                )
                > 0
            )
            .then(
                pl.col("spend")
                / pl.col(
                    "platform_conversions"
                )
            )
            .otherwise(None)
            .alias(
                "platform_reported_cpl"
            ),

            pl.when(
                pl.col(
                    "raw_marketing_records"
                )
                > 0
            )
            .then(
                pl.col("spend")
                / pl.col(
                    "raw_marketing_records"
                )
            )
            .otherwise(None)
            .alias(
                "raw_marketing_cpl"
            ),

            pl.when(
                pl.col(
                    "raw_crm_records"
                )
                > 0
            )
            .then(
                pl.col("spend")
                / pl.col(
                    "raw_crm_records"
                )
            )
            .otherwise(None)
            .alias(
                "raw_crm_cpl"
            ),

            pl.when(
                pl.col(
                    "reconciled_leads"
                )
                > 0
            )
            .then(
                pl.col("spend")
                / pl.col(
                    "reconciled_leads"
                )
            )
            .otherwise(None)
            .alias(
                "crm_confirmed_cpl"
            ),
        )
        .sort(
            "source_canonical"
        )
    )

    # --------------------------------------------------------
    # Campaign-level KPI audit
    # --------------------------------------------------------

    raw_marketing_campaign = (
        marketing
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                [
                    "Google Ads",
                    "Facebook Ads",
                ]
            )
        )
        .group_by(
            "source_canonical",
            "campaign",
        )
        .len()
        .rename(
            {
                "len": (
                    "raw_marketing_records"
                )
            }
        )
    )

    reconciled_campaign = (
        cluster_attribution
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                [
                    "Google Ads",
                    "Facebook Ads",
                ]
            )
        )
        .group_by(
            "source_canonical",
            "campaign",
        )
        .len()
        .rename(
            {
                "len": (
                    "reconciled_leads"
                )
            }
        )
    )

    spend_campaign = (
        spend
        .group_by(
            "source",
            "campaign",
        )
        .agg(
            pl.col("spend")
            .sum()
            .alias("spend"),

            pl.col(
                "platform_conversions"
            )
            .sum()
            .alias(
                "platform_conversions"
            ),

            pl.col("clicks")
            .sum()
            .alias("clicks"),

            pl.col("impressions")
            .sum()
            .alias("impressions"),
        )
        .rename(
            {
                "source": (
                    "source_canonical"
                )
            }
        )
    )

    campaign_report = (
        spend_campaign
        .join(
            raw_marketing_campaign,
            on=[
                "source_canonical",
                "campaign",
            ],
            how="left",
        )
        .join(
            reconciled_campaign,
            on=[
                "source_canonical",
                "campaign",
            ],
            how="left",
        )
        .with_columns(
            pl.col(
                "raw_marketing_records"
            )
            .fill_null(0),

            pl.col(
                "reconciled_leads"
            )
            .fill_null(0),
        )
        .with_columns(
            (
                pl.col("spend")
                / pl.col(
                    "platform_conversions"
                )
            )
            .alias(
                "platform_reported_cpl"
            ),

            (
                pl.col("spend")
                / pl.col(
                    "raw_marketing_records"
                )
            )
            .alias(
                "raw_marketing_cpl"
            ),

            (
                pl.col("spend")
                / pl.col(
                    "reconciled_leads"
                )
            )
            .alias(
                "crm_confirmed_cpl"
            ),
        )
        .sort(
            "spend",
            descending=True,
        )
    )

    # --------------------------------------------------------
    # Unresolved observable records
    # --------------------------------------------------------

    unmatched_crm = (
        crm
        .join(
            crm_members.select(
                "crm_record_id"
            ),
            on="crm_record_id",
            how="anti",
        )
        .filter(
            (
                pl.col(
                    "source_canonical"
                )
                .is_in(
                    TRACKABLE_SOURCES
                )
            )
            | (
                pl.col(
                    "source_canonical"
                )
                .is_null()
            )
        )
        .select(
            pl.lit("crm")
            .alias("system"),

            pl.col(
                "crm_record_id"
            )
            .alias("record_id"),

            pl.col("created_at")
            .alias("timestamp"),

            "name",
            "email",
            "phone",
            "zip_code",

            pl.col(
                "source_canonical"
            )
            .alias("source"),

            "campaign",
            "service",
        )
    )

    unmatched_marketing = (
        marketing
        .join(
            marketing_members.select(
                "marketing_record_id"
            ),
            on="marketing_record_id",
            how="anti",
        )
        .select(
            pl.lit("marketing")
            .alias("system"),

            pl.col(
                "marketing_record_id"
            )
            .alias("record_id"),

            pl.col("captured_at")
            .alias("timestamp"),

            "name",
            "email",
            "phone",
            "zip_code",

            pl.col(
                "source_canonical"
            )
            .alias("source"),

            "campaign",
            "service",
        )
    )

    unresolved = pl.concat(
        [
            unmatched_crm,
            unmatched_marketing,
        ],
        how="vertical",
    ).sort(
        [
            "system",
            "timestamp",
        ]
    )

    return (
        metrics,
        source_report,
        campaign_report,
        unresolved,
    )
