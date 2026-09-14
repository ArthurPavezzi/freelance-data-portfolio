from __future__ import annotations

import re
import unicodedata

import polars as pl


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = value.encode("ascii", "ignore").decode("ascii").lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        "",
        value,
    )

    return value or None


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip().lower()

    return value or None


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        return None

    return digits


def normalize_zip(value: str | None) -> str | None:
    if value is None:
        return None

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    if len(digits) < 5:
        return None

    return digits[:5]


def prepare_crm(
    crm: pl.DataFrame,
) -> pl.DataFrame:
    return crm.with_columns(
        pl.col("name")
        .map_elements(
            normalize_name,
            return_dtype=pl.String,
        )
        .alias("name_norm"),
        pl.col("email")
        .map_elements(
            normalize_email,
            return_dtype=pl.String,
        )
        .alias("email_norm"),
        pl.col("phone")
        .map_elements(
            normalize_phone,
            return_dtype=pl.String,
        )
        .alias("phone_norm"),
        pl.col("zip_code")
        .cast(pl.String)
        .map_elements(
            normalize_zip,
            return_dtype=pl.String,
        )
        .alias("zip_norm"),
    )


def prepare_marketing(
    marketing: pl.DataFrame,
) -> pl.DataFrame:
    return marketing.with_columns(
        pl.col("name")
        .map_elements(
            normalize_name,
            return_dtype=pl.String,
        )
        .alias("name_norm"),
        pl.col("email")
        .map_elements(
            normalize_email,
            return_dtype=pl.String,
        )
        .alias("email_norm"),
        pl.col("phone")
        .map_elements(
            normalize_phone,
            return_dtype=pl.String,
        )
        .alias("phone_norm"),
        pl.col("zip_code")
        .cast(pl.String)
        .map_elements(
            normalize_zip,
            return_dtype=pl.String,
        )
        .alias("zip_norm"),
    )
