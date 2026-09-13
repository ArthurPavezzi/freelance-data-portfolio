from __future__ import annotations

from typing import Any

import polars as pl

from .acquisition import PAID_SOURCES
from .report import TRACKABLE_SOURCES


def _build_observation_truth(
    crm_map: pl.DataFrame,
    marketing_map: pl.DataFrame,
) -> pl.DataFrame:
    crm_truth = (
        crm_map
        .select(
            pl.lit("crm").alias("system"),
            pl.col("crm_record_id")
            .alias("record_id"),
            "ground_truth_lead_id",
        )
    )

    marketing_truth = (
        marketing_map
        .select(
            pl.lit("marketing").alias("system"),
            pl.col("marketing_record_id")
            .alias("record_id"),
            "ground_truth_lead_id",
        )
    )

    return pl.concat(
        [
            crm_truth,
            marketing_truth,
        ],
        how="vertical",
    )


def _build_entity_truth(
    universe: pl.DataFrame,
    confirmed_membership: pl.DataFrame,
    singleton_membership: pl.DataFrame,
    observation_truth: pl.DataFrame,
) -> pl.DataFrame:
    """
    Map reconstructed acquisition entities back to hidden true leads.

    Used strictly for internal benchmark evaluation.
    """
    confirmed = (
        confirmed_membership
        .rename(
            {
                "reconciled_lead_id": (
                    "acquisition_entity_id"
                )
            }
        )
        .select(
            "acquisition_entity_id",
            "system",
            "record_id",
        )
    )

    singletons = (
        singleton_membership
        .rename(
            {
                "within_system_entity_id": (
                    "acquisition_entity_id"
                )
            }
        )
        .select(
            "acquisition_entity_id",
            "system",
            "record_id",
        )
    )

    memberships = (
        pl.concat(
            [
                confirmed,
                singletons,
            ],
            how="vertical",
        )
        .join(
            universe.select(
                "acquisition_entity_id"
            ),
            on="acquisition_entity_id",
            how="semi",
        )
    )

    mapped = memberships.join(
        observation_truth,
        on=[
            "system",
            "record_id",
        ],
        how="left",
    )

    entity_truth = (
        mapped
        .group_by(
            "acquisition_entity_id"
        )
        .agg(
            pl.col(
                "ground_truth_lead_id"
            )
            .drop_nulls()
            .n_unique()
            .alias(
                "n_ground_truth_leads"
            ),

            pl.col(
                "ground_truth_lead_id"
            )
            .drop_nulls()
            .first()
            .alias(
                "_truth_candidate"
            ),

            pl.len()
            .alias(
                "observation_count"
            ),
        )
        .with_columns(
            pl.when(
                pl.col(
                    "n_ground_truth_leads"
                )
                == 1
            )
            .then(
                pl.col(
                    "_truth_candidate"
                )
            )
            .otherwise(None)
            .alias(
                "ground_truth_lead_id"
            )
        )
        .drop(
            "_truth_candidate"
        )
    )

    return entity_truth


def build_internal_validation(
    universe: pl.DataFrame,
    confirmed_membership: pl.DataFrame,
    singleton_membership: pl.DataFrame,
    crm_map: pl.DataFrame,
    marketing_map: pl.DataFrame,
    leads: pl.DataFrame,
    spend: pl.DataFrame,
) -> tuple[
    dict[str, Any],
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Benchmark the reconstructed acquisition universe against hidden
    synthetic ground truth.

    IMPORTANT:
        This function is evaluation-only. Its outputs must never feed
        back into the operational reconciliation pipeline.
    """

    observation_truth = (
        _build_observation_truth(
            crm_map,
            marketing_map,
        )
    )

    entity_truth = (
        _build_entity_truth(
            universe,
            confirmed_membership,
            singleton_membership,
            observation_truth,
        )
    )

    lead_truth = (
        leads
        .select(
            pl.col("lead_id")
            .alias(
                "ground_truth_lead_id"
            ),
            pl.col("source")
            .alias(
                "true_source"
            ),
            pl.col("campaign")
            .alias(
                "true_campaign"
            ),
            pl.col("service")
            .alias(
                "true_service"
            ),
        )
    )

    entity_validation = (
        universe
        .join(
            entity_truth,
            on="acquisition_entity_id",
            how="left",
        )
        .with_columns(
            pl.col(
                "n_ground_truth_leads"
            )
            .fill_null(0)
            .cast(pl.Int64),

            pl.col(
                "observation_count"
            )
            .fill_null(0)
            .cast(pl.Int64),
        )
        .with_columns(
            (
                pl.col(
                    "n_ground_truth_leads"
                )
                == 1
            )
            .alias(
                "is_valid_entity"
            ),

            (
                pl.col(
                    "n_ground_truth_leads"
                )
                == 0
            )
            .alias(
                "is_unmapped_entity"
            ),

            (
                pl.col(
                    "n_ground_truth_leads"
                )
                > 1
            )
            .alias(
                "is_impure_entity"
            ),
        )
        .join(
            lead_truth,
            on="ground_truth_lead_id",
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col(
                    "is_valid_entity"
                )
            )
            .then(
                pl.col(
                    "source_canonical"
                )
                == pl.col(
                    "true_source"
                )
            )
            .otherwise(None)
            .alias(
                "source_correct"
            ),

            pl.when(
                pl.col(
                    "is_valid_entity"
                )
            )
            .then(
                pl.col("service")
                == pl.col(
                    "true_service"
                )
            )
            .otherwise(None)
            .alias(
                "service_correct"
            ),
        )
    )

    # --------------------------------------------------------
    # Overall reconstruction benchmark
    # --------------------------------------------------------

    true_trackable = (
        leads
        .filter(
            pl.col("source")
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .select(
            pl.col("lead_id")
            .alias(
                "ground_truth_lead_id"
            ),
            "source",
        )
    )

    valid_entities = (
        entity_validation
        .filter(
            pl.col(
                "is_valid_entity"
            )
        )
    )

    recovered_true_leads = (
        valid_entities
        .select(
            "ground_truth_lead_id"
        )
        .unique()
        .join(
            true_trackable.select(
                "ground_truth_lead_id"
            ),
            on="ground_truth_lead_id",
            how="inner",
        )
    )

    fragmentation = (
        valid_entities
        .group_by(
            "ground_truth_lead_id"
        )
        .len()
        .filter(
            pl.col("len") > 1
        )
    )

    reconstructed_entities = (
        universe.height
    )

    true_trackable_leads = (
        true_trackable.height
    )

    valid_entity_count = (
        valid_entities.height
    )

    unique_recovered = (
        recovered_true_leads.height
    )

    unmapped_entities = (
        entity_validation
        .filter(
            pl.col(
                "is_unmapped_entity"
            )
        )
        .height
    )

    impure_entities = (
        entity_validation
        .filter(
            pl.col(
                "is_impure_entity"
            )
        )
        .height
    )

    fragmented_true_leads = (
        fragmentation.height
    )

    duplicate_entity_excess = (
        valid_entity_count
        - unique_recovered
    )

    source_evaluable = (
        valid_entities
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_not_null()
            & pl.col(
                "true_source"
            )
            .is_not_null()
        )
    )

    correctly_attributed = int(
        source_evaluable[
            "source_correct"
        ].sum()
    )

    summary = {
        "true_trackable_leads": (
            true_trackable_leads
        ),
        "reconstructed_entities": (
            reconstructed_entities
        ),
        "valid_entities": (
            valid_entity_count
        ),
        "unique_true_leads_recovered": (
            unique_recovered
        ),
        "unmapped_entities": (
            unmapped_entities
        ),
        "impure_entities": (
            impure_entities
        ),
        "fragmented_true_leads": (
            fragmented_true_leads
        ),
        "duplicate_entity_excess": (
            duplicate_entity_excess
        ),
        "volume_error": (
            reconstructed_entities
            - true_trackable_leads
        ),
        "volume_absolute_error": abs(
            reconstructed_entities
            - true_trackable_leads
        ),
        "volume_relative_error": (
            (
                reconstructed_entities
                - true_trackable_leads
            )
            / true_trackable_leads
        ),
        "entity_validity_rate": (
            valid_entity_count
            / reconstructed_entities
            if reconstructed_entities
            else 0.0
        ),
        "unique_truth_per_entity": (
            unique_recovered
            / reconstructed_entities
            if reconstructed_entities
            else 0.0
        ),
        "lead_recall": (
            unique_recovered
            / true_trackable_leads
            if true_trackable_leads
            else 0.0
        ),
        "source_attribution_accuracy": (
            correctly_attributed
            / source_evaluable.height
            if source_evaluable.height
            else 0.0
        ),
    }

    # --------------------------------------------------------
    # Source-level validation
    # --------------------------------------------------------

    truth_by_source = (
        leads
        .filter(
            pl.col("source")
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by("source")
        .len()
        .rename(
            {
                "source": (
                    "source_canonical"
                ),
                "len": (
                    "true_leads"
                ),
            }
        )
    )

    reconstructed_by_source = (
        universe
        .group_by(
            "source_canonical"
        )
        .len()
        .rename(
            {
                "len": (
                    "reconstructed_leads"
                )
            }
        )
    )

    recovered_by_source = (
        valid_entities
        .filter(
            pl.col("true_source")
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .select(
            "ground_truth_lead_id",
            "true_source",
        )
        .unique(
            subset=[
                "ground_truth_lead_id"
            ]
        )
        .group_by(
            "true_source"
        )
        .len()
        .rename(
            {
                "true_source": (
                    "source_canonical"
                ),
                "len": (
                    "unique_true_leads_recovered"
                ),
            }
        )
    )

    attribution_by_source = (
        valid_entities
        .filter(
            pl.col("true_source")
            .is_in(
                TRACKABLE_SOURCES
            )
        )
        .group_by(
            "true_source"
        )
        .agg(
            pl.len()
            .alias(
                "valid_entities"
            ),

            pl.col(
                "source_correct"
            )
            .sum()
            .alias(
                "correctly_attributed_entities"
            ),
        )
        .rename(
            {
                "true_source": (
                    "source_canonical"
                )
            }
        )
    )

    source_validation = (
        truth_by_source
        .join(
            reconstructed_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            recovered_by_source,
            on="source_canonical",
            how="left",
        )
        .join(
            attribution_by_source,
            on="source_canonical",
            how="left",
        )
        .with_columns(
            pl.col(
                "reconstructed_leads"
            )
            .fill_null(0),

            pl.col(
                "unique_true_leads_recovered"
            )
            .fill_null(0),

            pl.col(
                "valid_entities"
            )
            .fill_null(0),

            pl.col(
                "correctly_attributed_entities"
            )
            .fill_null(0),
        )
        .with_columns(
            (
                pl.col(
                    "reconstructed_leads"
                ).cast(pl.Int64)
                - pl.col(
                    "true_leads"
                ).cast(pl.Int64)
            )
            .alias(
                "volume_error"
            ),

            (
                (
                    pl.col(
                        "reconstructed_leads"
                    ).cast(pl.Int64)
                    - pl.col(
                        "true_leads"
                    ).cast(pl.Int64)
                )
                / pl.col(
                    "true_leads"
                ).cast(pl.Float64)
            )
            .alias(
                "volume_error_rate"
            ),

            (
                pl.col(
                    "unique_true_leads_recovered"
                )
                / pl.col(
                    "true_leads"
                )
            )
            .alias(
                "lead_recall"
            ),

            pl.when(
                pl.col(
                    "valid_entities"
                )
                > 0
            )
            .then(
                pl.col(
                    "correctly_attributed_entities"
                )
                / pl.col(
                    "valid_entities"
                )
            )
            .otherwise(None)
            .alias(
                "source_attribution_accuracy"
            ),
        )
        .sort(
            "true_leads",
            descending=True,
        )
    )

    # --------------------------------------------------------
    # Paid KPI validation
    # --------------------------------------------------------

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
        )
        .rename(
            {
                "source": (
                    "source_canonical"
                )
            }
        )
    )

    true_paid = (
        truth_by_source
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                PAID_SOURCES
            )
        )
    )

    reconstructed_paid = (
        reconstructed_by_source
        .filter(
            pl.col(
                "source_canonical"
            )
            .is_in(
                PAID_SOURCES
            )
        )
    )

    paid_validation = (
        paid_spend
        .join(
            true_paid,
            on="source_canonical",
            how="left",
        )
        .join(
            reconstructed_paid,
            on="source_canonical",
            how="left",
        )
        .with_columns(
            (
                pl.col("spend")
                / pl.col(
                    "true_leads"
                )
            )
            .alias(
                "true_cpl"
            ),

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
                    "reconstructed_leads"
                )
            )
            .alias(
                "reconstructed_cpl"
            ),
        )
        .with_columns(
            (
                pl.col(
                    "reconstructed_cpl"
                )
                - pl.col(
                    "true_cpl"
                )
            )
            .alias(
                "reconstructed_cpl_error"
            ),

            (
                (
                    pl.col(
                        "reconstructed_cpl"
                    )
                    - pl.col(
                        "true_cpl"
                    )
                )
                / pl.col(
                    "true_cpl"
                )
            )
            .alias(
                "reconstructed_cpl_error_rate"
            ),

            (
                pl.col(
                    "platform_reported_cpl"
                )
                - pl.col(
                    "true_cpl"
                )
            )
            .alias(
                "platform_cpl_error"
            ),

            (
                (
                    pl.col(
                        "platform_reported_cpl"
                    )
                    - pl.col(
                        "true_cpl"
                    )
                )
                / pl.col(
                    "true_cpl"
                )
            )
            .alias(
                "platform_cpl_error_rate"
            ),
        )
        .sort(
            "source_canonical"
        )
    )

    return (
        summary,
        entity_validation,
        source_validation,
        paid_validation,
    )

def validation_summary_frame(
    summary: dict[str, Any],
) -> pl.DataFrame:
    return pl.DataFrame(
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
