import polars as pl

from crm_reconciliation.resolve import (
    build_manual_review_queue,
    resolve_matches,
)


def _exact_matches() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "crm_record_id": [
                "CRM1",
            ],
            "marketing_record_id": [
                "MKT1",
            ],
            "time_delta_minutes": [
                2,
            ],
            "match_rule": [
                "email_time",
            ],
            "match_score": [
                0.95,
            ],
        }
    )


def _fuzzy_candidates() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "crm_record_id": [
                "CRM2",
                "CRM3",
                "CRM4",
            ],
            "marketing_record_id": [
                "MKT2",
                "MKT3",
                "MKT4",
            ],
            "created_at": [
                None,
                None,
                None,
            ],
            "captured_at": [
                None,
                None,
                None,
            ],
            "crm_name": [
                "Alice Smith",
                "Bob Jones",
                "Carol Lee",
            ],
            "marketing_name": [
                "Alic Smith",
                "B. Jones",
                "C Lee",
            ],
            "crm_email": [
                "a@example.com",
                "b@example.com",
                "c@example.com",
            ],
            "marketing_email": [
                "aa@example.com",
                "bb@example.com",
                "cc@example.com",
            ],
            "crm_phone": [
                "2101111111",
                "2102222222",
                "2103333333",
            ],
            "marketing_phone": [
                "2101111112",
                "2102222223",
                "2103333334",
            ],
            "crm_zip": [
                "78201",
                "78202",
                "78203",
            ],
            "marketing_zip": [
                "78201",
                "78202",
                "78203",
            ],
            "service": [
                "Interior Painting",
                "Exterior Painting",
                "Cabinet Painting",
            ],
            "time_delta_minutes": [
                5,
                10,
                15,
            ],
            "name_similarity": [
                0.95,
                0.85,
                0.70,
            ],
            "email_similarity": [
                0.95,
                0.85,
                0.70,
            ],
            "phone_similarity": [
                0.95,
                0.85,
                0.70,
            ],
            "zip_similarity": [
                1.0,
                1.0,
                1.0,
            ],
            "identity_score": [
                0.96,
                0.84,
                0.70,
            ],
            "time_score": [
                0.97,
                0.95,
                0.92,
            ],
            "evidence_count": [
                4,
                4,
                4,
            ],
            "evidence_weight": [
                1.0,
                1.0,
                1.0,
            ],
            "fuzzy_score": [
                0.94,
                0.84,
                0.70,
            ],
        }
    )


def test_exact_matches_are_auto_matched() -> None:
    resolved = resolve_matches(
        _exact_matches(),
        _fuzzy_candidates(),
    )

    exact = resolved.filter(
        pl.col("match_method")
        == "exact"
    )

    assert exact.height == 1

    assert (
        exact[
            "review_status"
        ][0]
        == "auto_match"
    )


def test_high_fuzzy_score_is_auto_match() -> None:
    resolved = resolve_matches(
        _exact_matches(),
        _fuzzy_candidates(),
    )

    fuzzy_auto = resolved.filter(
        (
            pl.col("match_method")
            == "fuzzy"
        )
        & (
            pl.col("review_status")
            == "auto_match"
        )
    )

    assert fuzzy_auto.height == 1

    assert (
        fuzzy_auto[
            "crm_record_id"
        ][0]
        == "CRM2"
    )


def test_middle_fuzzy_score_requires_review() -> None:
    resolved = resolve_matches(
        _exact_matches(),
        _fuzzy_candidates(),
    )

    review = resolved.filter(
        pl.col("review_status")
        == "manual_review"
    )

    assert review.height == 1

    assert (
        review[
            "crm_record_id"
        ][0]
        == "CRM3"
    )


def test_low_fuzzy_score_is_rejected() -> None:
    resolved = resolve_matches(
        _exact_matches(),
        _fuzzy_candidates(),
    )

    assert (
        "CRM4"
        not in resolved[
            "crm_record_id"
        ].to_list()
    )


def test_manual_review_queue_only_contains_review_band() -> None:
    queue = (
        build_manual_review_queue(
            _fuzzy_candidates()
        )
    )

    assert queue.height == 1

    assert (
        queue[
            "crm_record_id"
        ][0]
        == "CRM3"
    )
