from __future__ import annotations

import polars as pl


PAID_SOURCES = [
    "Google Ads",
    "Facebook Ads",
]


def build_reconstructed_acquisition_universe(
    triaged: pl.DataFrame,
    deduped_entities: pl.DataFrame,
) -> pl.DataFrame:
    """
    Build the observable acquisition universe used for KPI reporting.

    Included:
        - cross-system confirmed lead entities
        - deduplicated CRM-only trackable entities
        - deduplicated valid marketing-only entities

    Excluded:
        - obvious test/spam
        - out-of-scope CRM observations
        - unknown-source CRM entities
        - records pending manual review

    Hidden ground truth is never used.
    """

    confirmed = (
        triaged
        .filter(
            pl.col("triage_status")
            == "cross_system_confirmed"
        )
        .select(
            pl.col("ledger_id")
            .alias(
                "acquisition_entity_id"
            ),

            pl.lit(
                "cross_system_confirmed"
            )
            .alias(
                "acquisition_status"
            ),

            pl.lit(
                "cross_system"
            )
            .alias(
                "origin_system"
            ),

            "event_timestamp",
            "source_canonical",
            "campaign",
            "service",

            (
                pl.col("crm_record_count")
                + pl.col(
                    "marketing_record_count"
                )
            )
            .cast(pl.Int64)
            .alias(
                "source_record_count"
            ),

            pl.lit(
                "high"
            )
            .alias(
                "confidence_tier"
            ),
        )
    )

    crm_only = (
        deduped_entities
        .filter(
            (
                pl.col("system")
                == "crm"
            )
            & (
                pl.col("triage_status")
                == "crm_only_trackable"
            )
        )
        .select(
            pl.col(
                "within_system_entity_id"
            )
            .alias(
                "acquisition_entity_id"
            ),

            pl.lit(
                "crm_only_trackable"
            )
            .alias(
                "acquisition_status"
            ),

            pl.lit("crm")
            .alias(
                "origin_system"
            ),

            "event_timestamp",
            "source_canonical",
            "campaign",
            "service",

            pl.col("record_count")
            .cast(pl.Int64)
            .alias(
                "source_record_count"
            ),

            pl.lit(
                "medium"
            )
            .alias(
                "confidence_tier"
            ),
        )
    )

    marketing_only = (
        deduped_entities
        .filter(
            (
                pl.col("system")
                == "marketing"
            )
            & (
                pl.col("triage_status")
                == "marketing_only_valid"
            )
        )
        .select(
            pl.col(
                "within_system_entity_id"
            )
            .alias(
                "acquisition_entity_id"
            ),

            pl.lit(
                "marketing_only_valid"
            )
            .alias(
                "acquisition_status"
            ),

            pl.lit(
                "marketing"
            )
            .alias(
                "origin_system"
            ),

            "event_timestamp",
            "source_canonical",
            "campaign",
            "service",

            pl.col("record_count")
            .cast(pl.Int64)
            .alias(
                "source_record_count"
            ),

            pl.lit(
                "medium"
            )
            .alias(
                "confidence_tier"
            ),
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
                "acquisition_entity_id",
            ]
        )
    )


def build_acquisition_source_summary(
    universe: pl.DataFrame,
) -> pl.DataFrame:
    """
    Explain how the reconstructed lead count is composed by source.
    """
    return (
        universe
        .group_by(
            "source_canonical"
        )
        .agg(
            pl.len()
            .alias(
                "reconstructed_leads"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "cross_system_confirmed"
            )
            .sum()
            .alias(
                "cross_system_confirmed"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "crm_only_trackable"
            )
            .sum()
            .alias(
                "crm_only_entities"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "marketing_only_valid"
            )
            .sum()
            .alias(
                "marketing_only_entities"
            ),
        )
        .sort(
            "reconstructed_leads",
            descending=True,
        )
    )


def build_reconstructed_paid_kpis(
    universe: pl.DataFrame,
    spend: pl.DataFrame,
) -> pl.DataFrame:
    """
    Compare platform-reported conversions with the reconstructed
    acquisition universe for paid channels.
    """

    leads = (
        universe
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                PAID_SOURCES
            )
        )
        .group_by(
            "source_canonical"
        )
        .agg(
            pl.len()
            .alias(
                "reconstructed_leads"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "cross_system_confirmed"
            )
            .sum()
            .alias(
                "confirmed_leads"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "crm_only_trackable"
            )
            .sum()
            .alias(
                "crm_only_leads"
            ),

            (
                pl.col(
                    "acquisition_status"
                )
                == "marketing_only_valid"
            )
            .sum()
            .alias(
                "marketing_only_leads"
            ),
        )
    )

    paid_spend = (
        spend
        .filter(
            pl.col("source")
            .is_in(
                PAID_SOURCES
            )
        )
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

    return (
        paid_spend
        .join(
            leads,
            on="source_canonical",
            how="left",
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
                    "confirmed_leads"
                )
            )
            .alias(
                "crm_confirmed_cpl"
            ),

            (
                pl.col("spend")
                / pl.col(
                    "reconstructed_leads"
                )
            )
            .alias(
                "reconstructed_cpl"
            ),

            (
                pl.col(
                    "platform_conversions"
                )
                - pl.col(
                    "reconstructed_leads"
                )
            )
            .alias(
                "platform_conversion_gap"
            ),

            (
                (
                    pl.col(
                        "platform_conversions"
                    )
                    - pl.col(
                        "reconstructed_leads"
                    )
                )
                / pl.col(
                    "reconstructed_leads"
                )
            )
            .alias(
                "platform_conversion_gap_rate"
            ),
        )
        .sort(
            "source_canonical"
        )
    )
