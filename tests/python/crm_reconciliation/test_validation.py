import polars as pl
from crm_reconciliation.validation import (
    build_internal_validation,
)


def _inputs():
    leads = pl.DataFrame(
        {
            "lead_id": [
                "L1",
                "L2",
                "L3",
            ],
            "source": [
                "Google Ads",
                "Google Ads",
                "Facebook Ads",
            ],
            "campaign": [
                "G1",
                "G1",
                "F1",
            ],
            "service": [
                "Interior Painting",
                "Interior Painting",
                "Exterior Painting",
            ],
        }
    )

    universe = (
        pl.DataFrame(
            {
                "acquisition_entity_id": [
                    "RCL1",
                    "WCR1",
                    "WMK1",
                ],
                "source_canonical": [
                    "Google Ads",
                    "Google Ads",
                    "Facebook Ads",
                ],
                "campaign": [
                    "G1",
                    "G1",
                    "F1",
                ],
                "service": [
                    "Interior Painting",
                    "Interior Painting",
                    "Exterior Painting",
                ],
            }
        )
    )

    confirmed_membership = (
        pl.DataFrame(
            {
                "reconciled_lead_id": [
                    "RCL1",
                    "RCL1",
                ],
                "system": [
                    "crm",
                    "marketing",
                ],
                "record_id": [
                    "CRM1",
                    "MKT1",
                ],
            }
        )
    )

    singleton_membership = (
        pl.DataFrame(
            {
                "within_system_entity_id": [
                    "WCR1",
                    "WMK1",
                ],
                "record_id": [
                    "CRM2",
                    "MKT2",
                ],
                "record_count": [
                    1,
                    1,
                ],
                "system": [
                    "crm",
                    "marketing",
                ],
            }
        )
    )

    crm_map = pl.DataFrame(
        {
            "crm_record_id": [
                "CRM1",
                "CRM2",
            ],
            "ground_truth_lead_id": [
                "L1",
                "L2",
            ],
        }
    )

    marketing_map = pl.DataFrame(
        {
            "marketing_record_id": [
                "MKT1",
                "MKT2",
            ],
            "ground_truth_lead_id": [
                "L1",
                "L3",
            ],
        }
    )

    spend = pl.DataFrame(
        {
            "source": [
                "Google Ads",
                "Facebook Ads",
            ],
            "spend": [
                200.0,
                100.0,
            ],
            "platform_conversions": [
                3,
                2,
            ],
        }
    )

    return (
        universe,
        confirmed_membership,
        singleton_membership,
        crm_map,
        marketing_map,
        leads,
        spend,
    )


def test_perfect_reconstruction_recovers_all_true_leads() -> None:
    summary, _, _, _ = (
        build_internal_validation(
            *_inputs()
        )
    )

    assert (
        summary[
            "true_trackable_leads"
        ]
        == 3
    )

    assert (
        summary[
            "unique_true_leads_recovered"
        ]
        == 3
    )

    assert (
        summary[
            "lead_recall"
        ]
        == 1.0
    )


def test_valid_entities_map_to_one_true_lead() -> None:
    summary, entity_validation, _, _ = (
        build_internal_validation(
            *_inputs()
        )
    )

    assert (
        summary[
            "unmapped_entities"
        ]
        == 0
    )

    assert (
        summary[
            "impure_entities"
        ]
        == 0
    )

    assert (
        entity_validation[
            "is_valid_entity"
        ].all()
    )


def test_source_attribution_is_correct() -> None:
    summary, _, _, _ = (
        build_internal_validation(
            *_inputs()
        )
    )

    assert (
        summary[
            "source_attribution_accuracy"
        ]
        == 1.0
    )


def test_reconstructed_cpl_matches_truth_when_counts_match() -> None:
    _, _, _, paid = (
        build_internal_validation(
            *_inputs()
        )
    )

    google = paid.filter(
        pl.col(
            "source_canonical"
        )
        == "Google Ads"
    )

    assert (
        google[
            "true_leads"
        ][0]
        == 2
    )

    assert (
        google[
            "reconstructed_leads"
        ][0]
        == 2
    )

    assert (
        google[
            "true_cpl"
        ][0]
        == 100.0
    )

    assert (
        google[
            "reconstructed_cpl"
        ][0]
        == 100.0
    )

from crm_reconciliation.validation import (
    validation_summary_frame,
)


def test_validation_summary_accepts_mixed_numeric_types() -> None:
    summary = {
        "true_leads": 8972,
        "volume_error": -40,
        "volume_relative_error": -0.004458,
        "lead_recall": 0.9955,
    }

    frame = validation_summary_frame(
        summary
    )

    assert frame.height == 4

    assert (
        frame.schema["value"]
        == pl.Float64
    )

    assert (
        frame
        .filter(
            pl.col("metric")
            == "volume_relative_error"
        )["value"][0]
        == -0.004458
    )

def test_source_volume_error_can_be_negative() -> None:
    (
        _,
        _,
        source_validation,
        _,
    ) = build_internal_validation(
        *_inputs()
    )

    google = source_validation.filter(
        pl.col("source_canonical")
        == "Google Ads"
    )

    assert (
        google.schema[
            "volume_error"
        ]
        == pl.Int64
    )
