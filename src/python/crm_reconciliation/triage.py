from __future__ import annotations

import polars as pl


def triage_ledger(
    ledger: pl.DataFrame,
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
) -> pl.DataFrame:
    """
    Classify unresolved observations using only observable system data.

    This layer does not use hidden ground-truth identifiers.
    """

    marketing_context = marketing.select(
        "marketing_record_id",
        pl.col("name").alias("marketing_name"),
        pl.col("email").alias("marketing_email"),
        pl.col("phone").alias("marketing_phone"),
    )

    result = (
        ledger.join(
            marketing_context,
            left_on="primary_marketing_record_id",
            right_on="marketing_record_id",
            how="left",
        )
        .with_columns(
            pl.col("marketing_name").fill_null("").str.to_lowercase().alias("_name_lower"),
            pl.col("marketing_email").fill_null("").str.to_lowercase().alias("_email_lower"),
            pl.col("marketing_phone")
            .fill_null("")
            .str.replace_all(
                r"\D",
                "",
            )
            .alias("_phone_digits"),
        )
        .with_columns(
            (
                pl.col("_name_lower").str.contains(r"\btest\b")
                | pl.col("_email_lower").str.contains(r"^test\d*@")
            ).alias("_looks_like_test"),
            (
                pl.col("_name_lower").str.contains(r"promotional contact")
                | pl.col("_email_lower").str.contains(r"^promo\d*@")
                | pl.col("_phone_digits").str.starts_with("210555")
            ).alias("_looks_like_spam"),
        )
        .with_columns(
            pl.when(pl.col("ledger_status") == "cross_system_confirmed")
            .then(pl.lit("cross_system_confirmed"))
            .when(pl.col("ledger_status") == "manual_review_pending")
            .then(pl.lit("manual_review_pending"))
            .when((pl.col("ledger_status") == "marketing_only") & pl.col("_looks_like_test"))
            .then(pl.lit("marketing_test"))
            .when((pl.col("ledger_status") == "marketing_only") & pl.col("_looks_like_spam"))
            .then(pl.lit("marketing_likely_spam"))
            .when(pl.col("ledger_status") == "marketing_only")
            .then(pl.lit("marketing_only_valid"))
            .when((pl.col("ledger_status") == "crm_only") & ~pl.col("in_marketing_scope"))
            .then(pl.lit("crm_only_out_of_scope"))
            .when((pl.col("ledger_status") == "crm_only") & pl.col("source_canonical").is_null())
            .then(pl.lit("crm_only_unknown_source"))
            .when(pl.col("ledger_status") == "crm_only")
            .then(pl.lit("crm_only_trackable"))
            .otherwise(pl.lit("unclassified"))
            .alias("triage_status")
        )
        .with_columns(
            pl.when(pl.col("triage_status") == "cross_system_confirmed")
            .then(pl.lit("accept"))
            .when(pl.col("triage_status") == "marketing_only_valid")
            .then(pl.lit("retain_as_unmatched_acquisition"))
            .when(pl.col("triage_status") == "crm_only_trackable")
            .then(pl.lit("investigate_tracking_gap"))
            .when(pl.col("triage_status") == "crm_only_unknown_source")
            .then(pl.lit("investigate_source"))
            .when(pl.col("triage_status") == "crm_only_out_of_scope")
            .then(pl.lit("exclude_from_marketing_reconciliation"))
            .when(
                pl.col("triage_status").is_in(
                    [
                        "marketing_test",
                        "marketing_likely_spam",
                    ]
                )
            )
            .then(pl.lit("exclude_from_lead_kpis"))
            .when(pl.col("triage_status") == "manual_review_pending")
            .then(pl.lit("manual_review"))
            .otherwise(pl.lit("investigate"))
            .alias("recommended_action")
        )
        .drop(
            "_name_lower",
            "_email_lower",
            "_phone_digits",
            "_looks_like_test",
            "_looks_like_spam",
        )
    )

    return result
