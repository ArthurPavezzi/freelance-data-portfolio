import polars as pl
from crm_reconciliation.triage import (
    triage_ledger,
)


def _ledger() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ledger_id": [
                "RCL1",
                "M1",
                "M2",
                "M3",
                "C1",
                "C2",
                "C3",
                "R1",
            ],
            "ledger_status": [
                "cross_system_confirmed",
                "marketing_only",
                "marketing_only",
                "marketing_only",
                "crm_only",
                "crm_only",
                "crm_only",
                "manual_review_pending",
            ],
            "primary_marketing_record_id": [
                "MKT1",
                "MKT2",
                "MKT3",
                "MKT4",
                None,
                None,
                None,
                "MKT5",
            ],
            "source_canonical": [
                "Google Ads",
                "Google Ads",
                "Facebook Ads",
                "Google Ads",
                "Referral",
                "Google Ads",
                None,
                "Google Ads",
            ],
            "in_marketing_scope": [
                True,
                True,
                True,
                True,
                False,
                True,
                True,
                True,
            ],
        }
    )


def _marketing() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "marketing_record_id": [
                "MKT1",
                "MKT2",
                "MKT3",
                "MKT4",
                "MKT5",
            ],
            "name": [
                "Alice Smith",
                "Test Lead",
                "Promotional Contact",
                "Bob Jones",
                "Carol Lee",
            ],
            "email": [
                "alice@example.com",
                "test1@example.com",
                "promo1@example.net",
                "bob@example.com",
                "carol@example.com",
            ],
            "phone": [
                "2101111111",
                None,
                "2105550001",
                "2102222222",
                "2103333333",
            ],
        }
    )


def _crm() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "crm_record_id": [],
        },
        schema={
            "crm_record_id": pl.String,
        },
    )


def test_marketing_test_is_detected() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert triaged.filter(pl.col("ledger_id") == "M1")["triage_status"][0] == "marketing_test"


def test_marketing_spam_is_detected() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert (
        triaged.filter(pl.col("ledger_id") == "M2")["triage_status"][0] == "marketing_likely_spam"
    )


def test_valid_marketing_only_is_retained() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert triaged.filter(pl.col("ledger_id") == "M3")["triage_status"][0] == "marketing_only_valid"


def test_out_of_scope_crm_is_excluded() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert (
        triaged.filter(pl.col("ledger_id") == "C1")["triage_status"][0] == "crm_only_out_of_scope"
    )


def test_trackable_crm_only_is_flagged() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert triaged.filter(pl.col("ledger_id") == "C2")["triage_status"][0] == "crm_only_trackable"


def test_unknown_crm_source_is_flagged() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert (
        triaged.filter(pl.col("ledger_id") == "C3")["triage_status"][0] == "crm_only_unknown_source"
    )


def test_manual_review_status_is_preserved() -> None:
    triaged = triage_ledger(
        _ledger(),
        _crm(),
        _marketing(),
    )

    assert (
        triaged.filter(pl.col("ledger_id") == "R1")["triage_status"][0] == "manual_review_pending"
    )
