from __future__ import annotations

import math
import re
import unicodedata

import polars as pl
from rapidfuzz.fuzz import ratio

MAX_TIME_DELTA_MINUTES = 24 * 60


def _text(value: object) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def _normalize_text(
    value: object,
) -> str | None:
    value = _text(value)

    if value is None:
        return None

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = value.encode("ascii", "ignore").decode("ascii").lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "",
        value,
    )

    return value or None


def _normalize_email(
    value: object,
) -> str | None:
    value = _text(value)

    if value is None:
        return None

    return value.lower()


def _normalize_phone_loose(
    value: object,
) -> str | None:
    value = _text(value)

    if value is None:
        return None

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    # Unlike exact normalization, preserve malformed
    # 9-digit etc. numbers for fuzzy comparison.
    return digits or None


def _normalize_zip_loose(
    value: object,
) -> str | None:
    value = _text(value)

    if value is None:
        return None

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    return digits or None


def _similarity(
    left: str | None,
    right: str | None,
) -> float | None:
    if left is None or right is None:
        return None

    return (
        ratio(
            left,
            right,
        )
        / 100.0
    )


def _score_pair(
    row: dict,
) -> dict[str, float | int | None]:
    name_similarity = _similarity(
        _normalize_text(row["crm_name"]),
        _normalize_text(row["marketing_name"]),
    )

    email_similarity = _similarity(
        _normalize_email(row["crm_email"]),
        _normalize_email(row["marketing_email"]),
    )

    phone_similarity = _similarity(
        _normalize_phone_loose(row["crm_phone"]),
        _normalize_phone_loose(row["marketing_phone"]),
    )

    zip_similarity = _similarity(
        _normalize_zip_loose(row["crm_zip"]),
        _normalize_zip_loose(row["marketing_zip"]),
    )

    similarities = {
        "email": (
            email_similarity,
            0.35,
        ),
        "phone": (
            phone_similarity,
            0.30,
        ),
        "name": (
            name_similarity,
            0.20,
        ),
        "zip": (
            zip_similarity,
            0.15,
        ),
    }

    available = [
        (similarity, weight)
        for similarity, weight in similarities.values()
        if similarity is not None
    ]

    evidence_count = len(available)

    evidence_weight = sum(weight for _, weight in available)

    if evidence_weight > 0:
        identity_score = (
            sum(similarity * weight for similarity, weight in available) / evidence_weight
        )
    else:
        identity_score = None

    time_delta = float(row["time_delta_minutes"])

    # Strong preference for temporally close events.
    # ~0.995 at 1 minute,
    # ~0.72 at 60 minutes,
    # ~0.37 at 180 minutes.
    time_score = math.exp(-time_delta / 180.0)

    if identity_score is None:
        fuzzy_score = 0.0
    else:
        fuzzy_score = 0.85 * identity_score + 0.15 * time_score

    return {
        "name_similarity": (name_similarity),
        "email_similarity": (email_similarity),
        "phone_similarity": (phone_similarity),
        "zip_similarity": (zip_similarity),
        "identity_score": (identity_score),
        "time_score": (time_score),
        "evidence_count": (evidence_count),
        "evidence_weight": (evidence_weight),
        "fuzzy_score": (fuzzy_score),
    }


def generate_fuzzy_candidates(
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
    exact_matches: pl.DataFrame,
) -> pl.DataFrame:
    """
    Generate plausible CRM ↔ marketing pairs using blocking.

    Candidate generation does not use hidden ground-truth IDs.

    Blocking:
        - same service
        - timestamps within ±24 hours

    Exact pairs already recovered by the deterministic matcher
    are excluded, but records themselves remain eligible because
    legitimate duplicate observations can create many-to-many links.
    """
    crm_block = (
        crm.select(
            "crm_record_id",
            "created_at",
            "name",
            "email",
            "phone",
            "zip_code",
            "service",
        )
        .rename(
            {
                "name": "crm_name",
                "email": "crm_email",
                "phone": "crm_phone",
                "zip_code": "crm_zip",
            }
        )
        .with_columns(pl.col("created_at").dt.date().alias("match_date"))
    )

    marketing_base = (
        marketing.select(
            "marketing_record_id",
            "captured_at",
            "name",
            "email",
            "phone",
            "zip_code",
            "service",
        )
        .rename(
            {
                "name": "marketing_name",
                "email": "marketing_email",
                "phone": "marketing_phone",
                "zip_code": "marketing_zip",
            }
        )
        .with_columns(pl.col("captured_at").dt.date().alias("captured_date"))
    )

    # Expand each marketing observation to the previous,
    # same, and following calendar day so ±24h matches
    # crossing midnight are not lost.
    marketing_block = pl.concat(
        [
            marketing_base.with_columns(
                (pl.col("captured_date") + pl.duration(days=offset)).alias("match_date")
            )
            for offset in (
                -1,
                0,
                1,
            )
        ],
        how="vertical",
    )

    candidates = (
        crm_block.join(
            marketing_block,
            on=[
                "service",
                "match_date",
            ],
            how="inner",
        )
        .with_columns(
            (pl.col("created_at") - pl.col("captured_at"))
            .abs()
            .dt.total_minutes()
            .alias("time_delta_minutes")
        )
        .filter(pl.col("time_delta_minutes") <= MAX_TIME_DELTA_MINUTES)
        .unique(
            subset=[
                "crm_record_id",
                "marketing_record_id",
            ]
        )
    )

    # Remove pairs already solved exactly,
    # not the underlying records.
    candidates = candidates.join(
        exact_matches.select(
            "crm_record_id",
            "marketing_record_id",
        ),
        on=[
            "crm_record_id",
            "marketing_record_id",
        ],
        how="anti",
    )

    return candidates


def score_fuzzy_candidates(
    candidates: pl.DataFrame,
) -> pl.DataFrame:
    score_fields = [
        "crm_name",
        "marketing_name",
        "crm_email",
        "marketing_email",
        "crm_phone",
        "marketing_phone",
        "crm_zip",
        "marketing_zip",
        "time_delta_minutes",
    ]

    return candidates.with_columns(
        pl.struct(score_fields)
        .map_elements(
            _score_pair,
            return_dtype=pl.Struct(
                [
                    pl.Field(
                        "name_similarity",
                        pl.Float64,
                    ),
                    pl.Field(
                        "email_similarity",
                        pl.Float64,
                    ),
                    pl.Field(
                        "phone_similarity",
                        pl.Float64,
                    ),
                    pl.Field(
                        "zip_similarity",
                        pl.Float64,
                    ),
                    pl.Field(
                        "identity_score",
                        pl.Float64,
                    ),
                    pl.Field(
                        "time_score",
                        pl.Float64,
                    ),
                    pl.Field(
                        "evidence_count",
                        pl.Int64,
                    ),
                    pl.Field(
                        "evidence_weight",
                        pl.Float64,
                    ),
                    pl.Field(
                        "fuzzy_score",
                        pl.Float64,
                    ),
                ]
            ),
        )
        .alias("scores")
    ).unnest("scores")
