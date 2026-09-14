import polars as pl

from crm_reconciliation.dedupe import (
    deduplicate_singletons,
)


def _base_crm() -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                "crm_record_id": [
                    "CRM1",
                    "CRM2",
                    "CRM3",
                    "CRM4",
                ],
                "created_at": [
                    "2026-01-01T10:00:00",
                    "2026-01-01T10:00:00",
                    "2026-01-10T10:00:00",
                    "2026-01-10T10:00:00",
                ],
                "name": [
                    "Alice Smith",
                    "ALICE SMITH",
                    "Bob Jones",
                    "Bob Jones",
                ],
                "email": [
                    "alice@example.com",
                    "alice@example.com",
                    "bob@example.com",
                    "bob@example.com",
                ],
                "phone": [
                    "2101111111",
                    "(210) 111-1111",
                    "2102222222",
                    "2102222222",
                ],
                "zip_code": [
                    "78201",
                    "78201",
                    "78202",
                    "78202",
                ],
                "service": [
                    "Interior Painting",
                    "Interior Painting",
                    "Exterior Painting",
                    "Exterior Painting",
                ],
            }
        )
        .with_columns(
            pl.col("created_at")
            .str.to_datetime()
        )
    )


def _base_marketing() -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                "marketing_record_id": [
                    "MKT1",
                    "MKT2",
                    "MKT3",
                    "MKT4",
                ],
                "captured_at": [
                    "2026-01-01T12:00:00",
                    "2026-01-01T12:07:00",
                    "2026-01-20T09:00:00",
                    "2026-02-10T09:00:00",
                ],
                "name": [
                    "Carol Lee",
                    "Carol Lee",
                    "David Brown",
                    "David Brown",
                ],
                "email": [
                    "carol@example.com",
                    "carol@example.com",
                    "david@example.com",
                    "david@example.com",
                ],
                "phone": [
                    "2103333333",
                    "+1 210 333 3333",
                    "2104444444",
                    "2104444444",
                ],
                "zip_code": [
                    "78203",
                    "78203",
                    "78204",
                    "78204",
                ],
                "service": [
                    "Cabinet Painting",
                    "Cabinet Painting",
                    "Drywall Repair",
                    "Drywall Repair",
                ],
            }
        )
        .with_columns(
            pl.col("captured_at")
            .str.to_datetime()
        )
    )


def _triaged() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "primary_crm_record_id": [
                "CRM1",
                "CRM2",
                "CRM3",
                "CRM4",
                None,
                None,
                None,
                None,
            ],
            "primary_marketing_record_id": [
                None,
                None,
                None,
                None,
                "MKT1",
                "MKT2",
                "MKT3",
                "MKT4",
            ],
            "triage_status": [
                "crm_only_trackable",
                "crm_only_trackable",
                "crm_only_trackable",
                "manual_review_pending",
                "marketing_only_valid",
                "marketing_only_valid",
                "marketing_only_valid",
                "marketing_only_valid",
            ],
            "source_canonical": [
                "Google Ads",
                "Google Ads",
                "Organic Search",
                "Google Ads",
                "Facebook Ads",
                "Facebook Ads",
                "Google Ads",
                "Google Ads",
            ],
            "campaign": [
                "Search | Interior Painting",
                "Search | Interior Painting",
                "Organic Search",
                "Search | Exterior Painting",
                "Meta | Free Estimate",
                "Meta | Free Estimate",
                "Search | Drywall Repair",
                "Search | Drywall Repair",
            ],
            "service": [
                "Interior Painting",
                "Interior Painting",
                "Exterior Painting",
                "Exterior Painting",
                "Cabinet Painting",
                "Cabinet Painting",
                "Drywall Repair",
                "Drywall Repair",
            ],
            "event_timestamp": [
                "2026-01-01T10:00:00",
                "2026-01-01T10:00:00",
                "2026-01-10T10:00:00",
                "2026-01-10T10:00:00",
                "2026-01-01T12:00:00",
                "2026-01-01T12:07:00",
                "2026-01-20T09:00:00",
                "2026-02-10T09:00:00",
            ],
        }
    ).with_columns(
        pl.col("event_timestamp")
        .str.to_datetime()
    )


def test_crm_duplicate_records_are_collapsed() -> None:
    entities, membership = (
        deduplicate_singletons(
            _triaged(),
            _base_crm(),
            _base_marketing(),
        )
    )

    crm_entities = entities.filter(
        pl.col("system")
        == "crm"
    )

    duplicate_entity = (
        crm_entities
        .filter(
            pl.col("record_count")
            == 2
        )
    )

    assert duplicate_entity.height == 1

    entity_id = duplicate_entity[
        "within_system_entity_id"
    ][0]

    members = (
        membership
        .filter(
            pl.col(
                "within_system_entity_id"
            )
            == entity_id
        )[
            "record_id"
        ]
        .to_list()
    )

    assert set(members) == {
        "CRM1",
        "CRM2",
    }


def test_marketing_duplicates_within_time_window_are_collapsed() -> None:
    entities, membership = (
        deduplicate_singletons(
            _triaged(),
            _base_crm(),
            _base_marketing(),
        )
    )

    marketing_entities = (
        entities
        .filter(
            pl.col("system")
            == "marketing"
        )
    )

    duplicate_entity = (
        marketing_entities
        .filter(
            pl.col("record_count")
            == 2
        )
    )

    assert duplicate_entity.height == 1

    entity_id = duplicate_entity[
        "within_system_entity_id"
    ][0]

    members = (
        membership
        .filter(
            pl.col(
                "within_system_entity_id"
            )
            == entity_id
        )[
            "record_id"
        ]
        .to_list()
    )

    assert set(members) == {
        "MKT1",
        "MKT2",
    }


def test_distant_marketing_events_are_not_collapsed() -> None:
    entities, membership = (
        deduplicate_singletons(
            _triaged(),
            _base_crm(),
            _base_marketing(),
        )
    )

    mkt3 = membership.filter(
        pl.col("record_id")
        == "MKT3"
    )

    mkt4 = membership.filter(
        pl.col("record_id")
        == "MKT4"
    )

    assert mkt3.height == 1
    assert mkt4.height == 1

    assert (
        mkt3[
            "within_system_entity_id"
        ][0]
        != mkt4[
            "within_system_entity_id"
        ][0]
    )

    assert (
        entities
        .filter(
            pl.col(
                "within_system_entity_id"
            ).is_in(
                [
                    mkt3[
                        "within_system_entity_id"
                    ][0],
                    mkt4[
                        "within_system_entity_id"
                    ][0],
                ]
            )
        )[
            "record_count"
        ]
        .to_list()
        == [1, 1]
    )


def test_manual_review_records_are_excluded_from_dedupe() -> None:
    _, membership = (
        deduplicate_singletons(
            _triaged(),
            _base_crm(),
            _base_marketing(),
        )
    )

    assert (
        "CRM4"
        not in membership[
            "record_id"
        ].to_list()
    )
