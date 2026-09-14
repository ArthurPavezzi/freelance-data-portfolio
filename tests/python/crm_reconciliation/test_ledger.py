import polars as pl

from crm_reconciliation.ledger import (
    build_unified_ledger,
)


def _inputs():
    crm = pl.DataFrame(
        {
            "crm_record_id": [
                "CRM1",
                "CRM2",
                "CRM3",
            ],
            "created_at": [
                "2026-01-01T10:00:00",
                "2026-01-01T10:00:00",
                "2026-01-02T11:00:00",
            ],
            "source": [
                "Google PPC",
                "Google Ads",
                "Referral",
            ],
            "campaign": [
                "Search | Interior Painting",
                "Search | Interior Painting",
                "Customer Referral",
            ],
            "service": [
                "Interior Painting",
                "Interior Painting",
                "Exterior Painting",
            ],
        }
    ).with_columns(
        pl.col(
            "created_at"
        ).str.to_datetime()
    )

    marketing = pl.DataFrame(
        {
            "marketing_record_id": [
                "MKT1",
                "MKT2",
            ],
            "captured_at": [
                "2026-01-01T09:59:00",
                "2026-01-03T12:00:00",
            ],
            "source_label": [
                "google_paid",
                "meta_paid",
            ],
            "campaign": [
                "Search | Interior Painting",
                "Meta | Free Estimate",
            ],
            "service": [
                "Interior Painting",
                "Exterior Painting",
            ],
        }
    ).with_columns(
        pl.col(
            "captured_at"
        ).str.to_datetime()
    )

    clusters = pl.DataFrame(
        {
            "reconciled_lead_id": [
                "RCL0000001",
            ],
            "crm_record_count": [
                2,
            ],
            "marketing_record_count": [
                1,
            ],
            "match_edge_count": [
                2,
            ],
            "exact_edge_count": [
                2,
            ],
            "fuzzy_edge_count": [
                0,
            ],
            "has_crm_duplicates": [
                True,
            ],
            "has_marketing_duplicates": [
                False,
            ],
            "is_many_to_many": [
                False,
            ],
        }
    )

    membership = pl.DataFrame(
        {
            "reconciled_lead_id": [
                "RCL0000001",
                "RCL0000001",
                "RCL0000001",
            ],
            "system": [
                "crm",
                "crm",
                "marketing",
            ],
            "record_id": [
                "CRM1",
                "CRM2",
                "MKT1",
            ],
        }
    )

    resolved = pl.DataFrame(
        {
            "crm_record_id": [
                "CRM1",
                "CRM2",
                "CRM3",
            ],
            "marketing_record_id": [
                "MKT1",
                "MKT1",
                "MKT2",
            ],
            "review_status": [
                "auto_match",
                "auto_match",
                "manual_review",
            ],
        }
    )

    return (
        crm,
        marketing,
        clusters,
        membership,
        resolved,
    )


def test_confirmed_cluster_becomes_one_ledger_row() -> None:
    ledger = build_unified_ledger(
        *_inputs()
    )

    confirmed = ledger.filter(
        pl.col("ledger_status")
        == "cross_system_confirmed"
    )

    assert confirmed.height == 1

    assert (
        confirmed[
            "crm_record_count"
        ][0]
        == 2
    )

    assert (
        confirmed[
            "marketing_record_count"
        ][0]
        == 1
    )


def test_unmatched_records_remain_singletons() -> None:
    ledger = build_unified_ledger(
        *_inputs()
    )

    assert ledger.height == 3


def test_manual_review_records_are_marked_pending() -> None:
    ledger = build_unified_ledger(
        *_inputs()
    )

    pending = ledger.filter(
        pl.col(
            "ledger_status"
        )
        == "manual_review_pending"
    )

    assert pending.height == 2


def test_out_of_scope_crm_record_is_identified() -> None:
    ledger = build_unified_ledger(
        *_inputs()
    )

    crm3 = ledger.filter(
        pl.col(
            "primary_crm_record_id"
        )
        == "CRM3"
    )

    assert not crm3[
        "in_marketing_scope"
    ][0]


def test_confirmed_source_prefers_marketing_attribution() -> None:
    ledger = build_unified_ledger(
        *_inputs()
    )

    confirmed = ledger.filter(
        pl.col("ledger_status")
        == "cross_system_confirmed"
    )

    assert (
        confirmed[
            "source_canonical"
        ][0]
        == "Google Ads"
    )
