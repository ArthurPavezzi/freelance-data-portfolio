from __future__ import annotations

import polars as pl


def evaluate_matches(
    matches: pl.DataFrame,
    crm_map: pl.DataFrame,
    marketing_map: pl.DataFrame,
) -> tuple[
    dict[str, float | int],
    pl.DataFrame,
]:
    """
    Evaluate predicted cross-system links against hidden ground truth.
    """
    crm_truth = crm_map.select(
        "crm_record_id",
        pl.col(
            "ground_truth_lead_id"
        ).alias(
            "crm_true_lead_id"
        ),
    )

    marketing_truth = (
        marketing_map
        .filter(
            pl.col(
                "ground_truth_lead_id"
            ).is_not_null()
        )
        .select(
            "marketing_record_id",
            pl.col(
                "ground_truth_lead_id"
            ).alias(
                "marketing_true_lead_id"
            ),
        )
    )

    evaluated = (
        matches
        .join(
            crm_truth,
            on="crm_record_id",
            how="left",
        )
        .join(
            marketing_truth,
            on="marketing_record_id",
            how="left",
        )
        .with_columns(
            (
                pl.col(
                    "crm_true_lead_id"
                )
                == pl.col(
                    "marketing_true_lead_id"
                )
            )
            .fill_null(False)
            .alias("is_true_match")
        )
    )

    true_positives = (
        evaluated[
            "is_true_match"
        ].sum()
    )

    predicted = evaluated.height

    precision = (
        true_positives / predicted
        if predicted
        else 0.0
    )

    # --------------------------------------------------------
    # All observable true CRM ↔ marketing pairs
    # --------------------------------------------------------

    crm_observed = (
        crm_map
        .filter(
            pl.col(
                "ground_truth_lead_id"
            ).is_not_null()
        )
        .select(
            "crm_record_id",
            "ground_truth_lead_id",
        )
    )

    marketing_observed = (
        marketing_map
        .filter(
            pl.col(
                "ground_truth_lead_id"
            ).is_not_null()
        )
        .select(
            "marketing_record_id",
            "ground_truth_lead_id",
        )
    )

    possible_true_pairs = (
        crm_observed
        .join(
            marketing_observed,
            on="ground_truth_lead_id",
            how="inner",
        )
        .height
    )

    # --------------------------------------------------------
    # Lead-level recovery
    # --------------------------------------------------------
    
    observable_crm_leads = set(
        crm_observed[
            "ground_truth_lead_id"
        ].to_list()
    )
    
    observable_marketing_leads = set(
        marketing_observed[
            "ground_truth_lead_id"
        ].to_list()
    )
    
    observable_true_leads = (
        observable_crm_leads
        & observable_marketing_leads
    )
    
    recovered_true_leads = set(
        evaluated
        .filter(
            pl.col("is_true_match")
        )[
            "crm_true_lead_id"
        ]
        .drop_nulls()
        .to_list()
    )
    
    lead_level_recovered = len(
        observable_true_leads
        & recovered_true_leads
    )
    
    lead_level_possible = len(
        observable_true_leads
    )
    
    lead_level_recall = (
        lead_level_recovered
        / lead_level_possible
        if lead_level_possible
        else 0.0
    )

    recall = (
        true_positives
        / possible_true_pairs
        if possible_true_pairs
        else 0.0
    )

    f1 = (
        2
        * precision
        * recall
        / (
            precision
            + recall
        )
        if (
            precision
            + recall
        )
        else 0.0
    )

    metrics = {
        "pair_predicted": predicted,
        "pair_true_positives": int(
            true_positives
        ),
        "pair_possible": (
            possible_true_pairs
        ),
        "pair_precision": float(
            precision
        ),
        "pair_recall": float(
            recall
        ),
        "pair_f1": float(
            f1
        ),
        "lead_possible": (
            lead_level_possible
        ),
        "lead_recovered": (
            lead_level_recovered
        ),
        "lead_recall": float(
            lead_level_recall
        ),
    }

    return metrics, evaluated
