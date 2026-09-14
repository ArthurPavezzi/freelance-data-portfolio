from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl

from .config import SimulationConfig

TRACKABLE_SOURCES = {
    "Google Ads",
    "Facebook Ads",
    "Organic Search",
    "Direct",
}

CAPTURE_RATES = {
    "Google Ads": 0.985,
    "Facebook Ads": 0.980,
    "Organic Search": 0.920,
    "Direct": 0.800,
}

PLATFORM_BY_SOURCE = {
    "Google Ads": "Google Ads",
    "Facebook Ads": "Meta",
    "Organic Search": "Website Analytics",
    "Direct": "Website Analytics",
}

SOURCE_LABEL_BY_SOURCE = {
    "Google Ads": "google_paid",
    "Facebook Ads": "meta_paid",
    "Organic Search": "organic_search",
    "Direct": "direct_website",
}

FORM_BY_SOURCE = {
    "Google Ads": "Request an Estimate",
    "Facebook Ads": "Meta Lead Form",
    "Organic Search": "Website Estimate Form",
    "Direct": "Website Contact Form",
}

LANDING_PAGE_BY_SOURCE = {
    "Google Ads": "/estimate",
    "Facebook Ads": "/painting-offer",
    "Organic Search": "/services",
    "Direct": "/contact",
}

MARKETING_COLUMNS = [
    "marketing_record_id",
    "captured_at",
    "platform",
    "source_label",
    "campaign",
    "name",
    "email",
    "phone",
    "zip_code",
    "service",
    "form_name",
    "landing_page",
]


def _format_phone(
    phone: str,
    rng: np.random.Generator,
) -> str:
    if len(phone) != 10 or not phone.isdigit():
        return phone

    area = phone[:3]
    exchange = phone[3:6]
    subscriber = phone[6:]

    variants = [
        phone,
        f"{area}-{exchange}-{subscriber}",
        f"({area}) {exchange}-{subscriber}",
        f"+1 {area} {exchange} {subscriber}",
    ]

    return str(rng.choice(variants))


def _variant_name(
    name: str,
    rng: np.random.Generator,
) -> str:
    parts = name.split()

    if not parts:
        return name

    variants = [
        name.upper(),
        name.lower(),
        " ".join(parts),
    ]

    if len(parts) >= 2:
        variants.append(f"{parts[0][0]}. {' '.join(parts[1:])}")

    return str(rng.choice(variants))


def _jitter_timestamp(
    created_at: datetime,
    rng: np.random.Generator,
) -> datetime:
    """
    Simulate small differences between the true inquiry timestamp and
    the timestamp recorded by the marketing system.
    """
    jitter_minutes = int(
        np.clip(
            round(
                rng.normal(
                    loc=2.0,
                    scale=3.0,
                )
            ),
            -2,
            15,
        )
    )

    return created_at + timedelta(minutes=jitter_minutes)


def generate_marketing_export(
    leads: pl.DataFrame,
    customers: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Generate an imperfect marketing-system export from true leads.

    Only trackable acquisition sources are expected to appear here.
    Marketing records use system-specific identifiers and labels.

    Returns:
        marketing_export
        marketing_corruption_log
        marketing_observation_map
    """
    rng = np.random.default_rng(config.seed + 4)

    customer_lookup = {row["customer_id"]: row for row in customers.iter_rows(named=True)}

    export_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []

    record_number = 1
    corruption_number = 1

    def next_record_id() -> str:
        nonlocal record_number

        record_id = f"MKT{record_number:07d}"

        record_number += 1

        return record_id

    def log_event(
        *,
        marketing_record_id: str | None,
        lead_id: str | None,
        field: str,
        corruption_type: str,
        original_value: Any,
        corrupted_value: Any,
    ) -> None:
        nonlocal corruption_number

        log_rows.append(
            {
                "corruption_id": (f"MC{corruption_number:07d}"),
                "system": "marketing",
                "record_type": "lead",
                "marketing_record_id": (marketing_record_id),
                "ground_truth_lead_id": (lead_id),
                "field": field,
                "corruption_type": (corruption_type),
                "original_value": (None if original_value is None else str(original_value)),
                "corrupted_value": (None if corrupted_value is None else str(corrupted_value)),
            }
        )

        corruption_number += 1

    for lead in leads.iter_rows(named=True):
        source = str(lead["source"])

        if source not in TRACKABLE_SOURCES:
            continue

        lead_id = str(lead["lead_id"])

        customer_id = int(lead["customer_id"])

        capture_rate = CAPTURE_RATES[source]

        # ------------------------------------------------------------
        # Trackable lead not captured by marketing system
        # ------------------------------------------------------------

        if rng.random() >= capture_rate:
            log_event(
                marketing_record_id=None,
                lead_id=lead_id,
                field="record",
                corruption_type=("missing_marketing_record"),
                original_value=lead_id,
                corrupted_value=None,
            )

            continue

        customer = customer_lookup[customer_id]

        marketing_record_id = next_record_id()

        row: dict[str, Any] = {
            "marketing_record_id": (marketing_record_id),
            "captured_at": (
                _jitter_timestamp(
                    lead["created_at"],
                    rng,
                )
            ),
            "platform": (PLATFORM_BY_SOURCE[source]),
            "source_label": (SOURCE_LABEL_BY_SOURCE[source]),
            "campaign": lead["campaign"],
            "name": customer["canonical_name"],
            "email": customer["canonical_email"],
            "phone": customer["canonical_phone"],
            "zip_code": customer["zip_code"],
            "service": lead["service"],
            "form_name": (FORM_BY_SOURCE[source]),
            "landing_page": (LANDING_PAGE_BY_SOURCE[source]),
        }

        # ------------------------------------------------------------
        # Name representation noise
        # ------------------------------------------------------------

        if rng.random() < config.marketing_name_variant_rate:
            original = str(row["name"])

            variant = _variant_name(
                original,
                rng,
            )

            row["name"] = variant

            log_event(
                marketing_record_id=(marketing_record_id),
                lead_id=lead_id,
                field="name",
                corruption_type=("name_variant"),
                original_value=original,
                corrupted_value=variant,
            )

        # ------------------------------------------------------------
        # Email missingness
        # ------------------------------------------------------------

        if rng.random() < config.marketing_missing_email_rate:
            original = str(row["email"])

            row["email"] = None

            log_event(
                marketing_record_id=(marketing_record_id),
                lead_id=lead_id,
                field="email",
                corruption_type=("missing_email"),
                original_value=original,
                corrupted_value=None,
            )

        # ------------------------------------------------------------
        # Phone quality / representation
        # ------------------------------------------------------------

        phone_draw = rng.random()

        if phone_draw < config.marketing_missing_phone_rate:
            original = str(row["phone"])

            row["phone"] = None

            log_event(
                marketing_record_id=(marketing_record_id),
                lead_id=lead_id,
                field="phone",
                corruption_type=("missing_phone"),
                original_value=original,
                corrupted_value=None,
            )

        elif rng.random() < config.marketing_phone_format_rate:
            original = str(row["phone"])

            formatted = _format_phone(
                original,
                rng,
            )

            row["phone"] = formatted

            if formatted != original:
                log_event(
                    marketing_record_id=(marketing_record_id),
                    lead_id=lead_id,
                    field="phone",
                    corruption_type=("phone_format"),
                    original_value=original,
                    corrupted_value=formatted,
                )

        export_rows.append(row)

        mapping_rows.append(
            {
                "marketing_record_id": (marketing_record_id),
                "ground_truth_lead_id": (lead_id),
                "ground_truth_customer_id": (customer_id),
                "record_kind": ("true_lead"),
                "is_duplicate": False,
                "duplicate_of_marketing_record_id": (None),
            }
        )

        # ------------------------------------------------------------
        # Duplicate submission
        # ------------------------------------------------------------

        if rng.random() < config.marketing_duplicate_rate:
            duplicate_id = next_record_id()

            duplicate = row.copy()

            duplicate["marketing_record_id"] = duplicate_id

            duplicate["captured_at"] = row["captured_at"] + timedelta(
                minutes=int(
                    rng.integers(
                        1,
                        11,
                    )
                )
            )

            export_rows.append(duplicate)

            mapping_rows.append(
                {
                    "marketing_record_id": (duplicate_id),
                    "ground_truth_lead_id": (lead_id),
                    "ground_truth_customer_id": (customer_id),
                    "record_kind": ("duplicate"),
                    "is_duplicate": True,
                    "duplicate_of_marketing_record_id": (marketing_record_id),
                }
            )

            log_event(
                marketing_record_id=(duplicate_id),
                lead_id=lead_id,
                field="record",
                corruption_type=("duplicate_submission"),
                original_value=(marketing_record_id),
                corrupted_value=(duplicate_id),
            )

    # ------------------------------------------------------------
    # Synthetic noise records: test submissions and spam
    # ------------------------------------------------------------

    true_record_count = len(export_rows)

    n_test = int(
        rng.binomial(
            true_record_count,
            config.marketing_test_record_rate,
        )
    )

    n_spam = int(
        rng.binomial(
            true_record_count,
            config.marketing_spam_record_rate,
        )
    )

    if export_rows:
        template_indices = np.arange(len(export_rows))

        for noise_kind, count in [
            ("test", n_test),
            ("spam", n_spam),
        ]:
            for noise_index in range(
                1,
                count + 1,
            ):
                template = export_rows[int(rng.choice(template_indices))]

                record_id = next_record_id()

                noise = template.copy()

                noise["marketing_record_id"] = record_id

                noise["captured_at"] = template["captured_at"] + timedelta(
                    minutes=int(
                        rng.integers(
                            1,
                            60,
                        )
                    )
                )

                if noise_kind == "test":
                    noise["name"] = "Test Lead"
                    noise["email"] = f"test{noise_index}@example.com"
                    noise["phone"] = None

                else:
                    noise["name"] = "Promotional Contact"
                    noise["email"] = f"promo{noise_index}@example.net"
                    noise["phone"] = f"210555{noise_index % 10000:04d}"

                export_rows.append(noise)

                mapping_rows.append(
                    {
                        "marketing_record_id": (record_id),
                        "ground_truth_lead_id": (None),
                        "ground_truth_customer_id": (None),
                        "record_kind": (noise_kind),
                        "is_duplicate": False,
                        "duplicate_of_marketing_record_id": (None),
                    }
                )

                log_event(
                    marketing_record_id=(record_id),
                    lead_id=None,
                    field="record",
                    corruption_type=(f"{noise_kind}_record"),
                    original_value=None,
                    corrupted_value=(record_id),
                )

    marketing_export = pl.DataFrame(export_rows).select(MARKETING_COLUMNS)

    marketing_corruption_log = pl.DataFrame(log_rows)

    marketing_observation_map = pl.DataFrame(mapping_rows)

    return (
        marketing_export,
        marketing_corruption_log,
        marketing_observation_map,
    )
