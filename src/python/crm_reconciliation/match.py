from __future__ import annotations

import polars as pl

MAX_TIME_DELTA_MINUTES = 24 * 60


def _add_time_delta(
    candidates: pl.DataFrame,
) -> pl.DataFrame:
    return candidates.with_columns(
        (pl.col("created_at") - pl.col("captured_at"))
        .abs()
        .dt.total_minutes()
        .alias("time_delta_minutes")
    )


def _filter_time_window(
    candidates: pl.DataFrame,
) -> pl.DataFrame:
    return candidates.filter(pl.col("time_delta_minutes") <= MAX_TIME_DELTA_MINUTES)


def _candidate_join(
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
    *,
    on: list[str],
    rule: str,
    score: float,
) -> pl.DataFrame:
    left = crm.select(
        [
            "crm_record_id",
            "created_at",
            *on,
        ]
    )

    right = marketing.select(
        [
            "marketing_record_id",
            "captured_at",
            *on,
        ]
    )

    # Null identifiers should never create exact matches.
    for field in on:
        left = left.filter(pl.col(field).is_not_null())

        right = right.filter(pl.col(field).is_not_null())

    candidates = left.join(
        right,
        on=on,
        how="inner",
    )

    candidates = _add_time_delta(candidates)

    candidates = _filter_time_window(candidates)

    return candidates.select(
        "crm_record_id",
        "marketing_record_id",
        "time_delta_minutes",
    ).with_columns(
        pl.lit(rule).alias("match_rule"),
        pl.lit(score).alias("match_score"),
    )


def generate_exact_candidates(
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
) -> pl.DataFrame:
    """
    Generate deterministic cross-system candidate pairs.

    Matching combines normalized identity fields with temporal
    proximity so repeat customers are not automatically treated as
    the same lead event.
    """
    candidate_frames = [
        _candidate_join(
            crm,
            marketing,
            on=[
                "email_norm",
                "phone_norm",
            ],
            rule="email_phone_time",
            score=1.00,
        ),
        _candidate_join(
            crm,
            marketing,
            on=[
                "email_norm",
            ],
            rule="email_time",
            score=0.95,
        ),
        _candidate_join(
            crm,
            marketing,
            on=[
                "phone_norm",
            ],
            rule="phone_time",
            score=0.95,
        ),
        _candidate_join(
            crm,
            marketing,
            on=[
                "name_norm",
                "zip_norm",
            ],
            rule="name_zip_time",
            score=0.85,
        ),
    ]

    candidates = pl.concat(
        candidate_frames,
        how="vertical",
    )

    # The same pair may satisfy multiple rules.
    # Keep the strongest one.
    candidates = candidates.sort(
        [
            "match_score",
            "time_delta_minutes",
        ],
        descending=[
            True,
            False,
        ],
    ).unique(
        subset=[
            "crm_record_id",
            "marketing_record_id",
        ],
        keep="first",
    )

    return candidates
