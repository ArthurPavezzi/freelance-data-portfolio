import polars as pl

from crm_reconciliation.acquisition import (
    build_acquisition_source_summary,
    build_reconstructed_acquisition_universe,
    build_reconstructed_paid_kpis,
)


def _triaged() -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                "ledger_id": [
                    "RCL1",
                    "RCL2",
                ],
                "triage_status": [
                    "cross_system_confirmed",
                    "cross_system_confirmed",
                ],
                "event_timestamp": [
                    "2026-01-01T10:00:00",
                    "2026-01-02T10:00:00",
                ],
                "source_canonical": [
                    "Google Ads",
                    "Facebook Ads",
                ],
                "campaign": [
                    "Search | Interior Painting",
                    "Meta | Free Estimate",
                ],
                "service": [
                    "Interior Painting",
                    "Exterior Painting",
                ],
                "crm_record_count": [
                    2,
                    1,
                ],
                "marketing_record_count": [
                    1,
                    1,
                ],
            }
        )
        .with_columns(
            pl.col(
                "event_timestamp"
            )
            .str.to_datetime()
        )
    )


def _deduped() -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                "within_system_entity_id": [
                    "WCR1",
                    "WCR2",
                    "WMK1",
                    "WMK2",
                ],
                "system": [
                    "crm",
                    "crm",
                    "marketing",
                    "marketing",
                ],
                "record_count": [
                    2,
                    1,
                    2,
                    1,
                ],
                "event_timestamp": [
                    "2026-01-03T10:00:00",
                    "2026-01-04T10:00:00",
                    "2026-01-05T10:00:00",
                    "2026-01-06T10:00:00",
                ],
                "triage_status": [
                    "crm_only_trackable",
                    "crm_only_unknown_source",
                    "marketing_only_valid",
                    "marketing_only_valid",
                ],
                "source_canonical": [
                    "Google Ads",
                    None,
                    "Google Ads",
                    "Facebook Ads",
                ],
                "campaign": [
                    "Search | Interior Painting",
                    None,
                    "Search | Interior Painting",
                    "Meta | Free Estimate",
                ],
                "service": [
                    "Interior Painting",
                    "Interior Painting",
                    "Interior Painting",
                    "Exterior Painting",
                ],
            }
        )
        .with_columns(
            pl.col(
                "event_timestamp"
            )
            .str.to_datetime()
        )
    )


def test_reconstructed_universe_uses_entities_not_records() -> None:
    universe = (
        build_reconstructed_acquisition_universe(
            _triaged(),
            _deduped(),
        )
    )

    # 2 confirmed + WCR1 + WMK1 + WMK2.
    # WCR2 is unknown-source and excluded.
    assert universe.height == 5

    # WCR1 represents two CRM rows but one lead entity.
    assert (
        universe
        .filter(
            pl.col(
                "acquisition_entity_id"
            )
            == "WCR1"
        )
        .height
        == 1
    )


def test_unknown_source_crm_entity_is_excluded() -> None:
    universe = (
        build_reconstructed_acquisition_universe(
            _triaged(),
            _deduped(),
        )
    )

    assert (
        "WCR2"
        not in universe[
            "acquisition_entity_id"
        ].to_list()
    )


def test_source_summary_reconstructs_lead_composition() -> None:
    universe = (
        build_reconstructed_acquisition_universe(
            _triaged(),
            _deduped(),
        )
    )

    summary = (
        build_acquisition_source_summary(
            universe
        )
    )

    google = summary.filter(
        pl.col("source_canonical")
        == "Google Ads"
    )

    assert (
        google[
            "reconstructed_leads"
        ][0]
        == 3
    )

    assert (
        google[
            "cross_system_confirmed"
        ][0]
        == 1
    )

    assert (
        google[
            "crm_only_entities"
        ][0]
        == 1
    )

    assert (
        google[
            "marketing_only_entities"
        ][0]
        == 1
    )


def test_reconstructed_cpl_uses_entity_count() -> None:
    universe = (
        build_reconstructed_acquisition_universe(
            _triaged(),
            _deduped(),
        )
    )

    spend = pl.DataFrame(
        {
            "source": [
                "Google Ads",
                "Facebook Ads",
            ],
            "spend": [
                300.0,
                200.0,
            ],
            "platform_conversions": [
                4,
                3,
            ],
            "clicks": [
                100,
                80,
            ],
            "impressions": [
                1000,
                800,
            ],
        }
    )

    kpis = (
        build_reconstructed_paid_kpis(
            universe,
            spend,
        )
    )

    google = kpis.filter(
        pl.col("source_canonical")
        == "Google Ads"
    )

    # Three reconstructed Google acquisition entities.
    assert (
        google[
            "reconstructed_leads"
        ][0]
        == 3
    )

    assert (
        google[
            "reconstructed_cpl"
        ][0]
        == 100.0
    )
