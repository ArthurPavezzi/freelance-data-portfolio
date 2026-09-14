from __future__ import annotations

import string
from typing import Any

import numpy as np
import polars as pl

from .config import SimulationConfig


CRM_COLUMNS = [
    "crm_record_id",
    "created_at",
    "name",
    "email",
    "phone",
    "zip_code",
    "source",
    "campaign",
    "service",
    "salesperson_id",
    "response_minutes",
    "qualified",
    "estimate_id",
    "won",
    "funnel_stage",
]

SOURCE_ALIASES = {
    "Google Ads": [
        "Google",
        "Google PPC",
        "GAds",
        "Paid Search",
    ],
    "Facebook Ads": [
        "Facebook",
        "Meta Ads",
        "FB Ads",
        "Paid Social",
    ],
    "Organic Search": [
        "Organic",
        "SEO",
        "Google Organic",
    ],
    "Referral": [
        "Referral",
        "Customer Referral",
        "Ref",
    ],
    "Partner": [
        "Partner",
        "Partner Referral",
        "Strategic Partner",
    ],
    "Direct": [
        "Direct",
        "Website Direct",
        "Call In",
    ],
}


def _corrupt_name(
    name: str,
    rng: np.random.Generator,
) -> str:
    if len(name) < 4:
        return name

    variants: list[str] = []

    parts = name.split()

    # Drop a character.
    idx = int(
        rng.integers(
            1,
            len(name) - 1,
        )
    )

    variants.append(
        name[:idx]
        + name[idx + 1:]
    )

    # Swap adjacent characters.
    idx = int(
        rng.integers(
            0,
            len(name) - 1,
        )
    )

    chars = list(name)

    chars[idx], chars[idx + 1] = (
        chars[idx + 1],
        chars[idx],
    )

    variants.append(
        "".join(chars)
    )

    # Initial + surname.
    if len(parts) >= 2:
        variants.append(
            f"{parts[0][0]}. "
            f"{' '.join(parts[1:])}"
        )

    return str(
        rng.choice(variants)
    )


def _corrupt_zip(
    zip_code: str,
    rng: np.random.Generator,
) -> str:
    digits = list(
        str(zip_code)
    )

    if len(digits) != 5:
        return str(zip_code)

    corruption = str(
        rng.choice(
            [
                "swap",
                "replace",
                "drop",
            ]
        )
    )

    if corruption == "swap":
        idx = int(
            rng.integers(
                0,
                4,
            )
        )

        digits[idx], digits[idx + 1] = (
            digits[idx + 1],
            digits[idx],
        )

        return "".join(digits)

    if corruption == "replace":
        idx = int(
            rng.integers(
                0,
                5,
            )
        )

        original = digits[idx]

        alternatives = [
            str(x)
            for x in range(10)
            if str(x) != original
        ]

        digits[idx] = str(
            rng.choice(
                alternatives
            )
        )

        return "".join(digits)

    idx = int(
        rng.integers(
            0,
            5,
        )
    )

    del digits[idx]

    return "".join(digits)

    
def _alias_source(
    source: str,
    rng: np.random.Generator,
) -> str:
    """Return a plausible non-canonical CRM label for a lead source."""
    aliases = SOURCE_ALIASES.get(source)

    if not aliases:
        return source

    alternatives = [
        alias
        for alias in aliases
        if alias != source
    ]

    if not alternatives:
        return source

    return str(
        rng.choice(alternatives)
    )


def _format_phone(
    phone: str,
    rng: np.random.Generator,
) -> str:
    """
    Represent the same canonical US phone number in different formats.

    This is representation noise, not semantic corruption.
    """
    if len(phone) != 10 or not phone.isdigit():
        return phone

    area = phone[:3]
    exchange = phone[3:6]
    subscriber = phone[6:]

    variants = [
        phone,
        f"{area}-{exchange}-{subscriber}",
        f"({area}) {exchange}-{subscriber}",
        f"{area} {exchange} {subscriber}",
        f"+1 {area} {exchange} {subscriber}",
        f"+1 ({area}) {exchange}-{subscriber}",
    ]

    alternatives = [
        value
        for value in variants
        if value != phone
    ]

    return str(rng.choice(alternatives))


def _corrupt_phone(
    phone: str,
    rng: np.random.Generator,
) -> str:
    """
    Introduce an actual error into a canonical phone number.
    """
    digits = list(phone)

    if not digits:
        return phone

    operation = str(
        rng.choice(
            [
                "replace_digit",
                "drop_digit",
                "swap_digits",
            ]
        )
    )

    if operation == "replace_digit":
        position = int(
            rng.integers(0, len(digits))
        )

        original_digit = digits[position]

        alternatives = [
            digit
            for digit in string.digits
            if digit != original_digit
        ]

        digits[position] = str(
            rng.choice(alternatives)
        )

    elif (
        operation == "drop_digit"
        and len(digits) > 1
    ):
        position = int(
            rng.integers(0, len(digits))
        )
        del digits[position]

    elif (
        operation == "swap_digits"
        and len(digits) > 1
    ):
        position = int(
            rng.integers(0, len(digits) - 1)
        )

        digits[position], digits[position + 1] = (
            digits[position + 1],
            digits[position],
        )

    corrupted = "".join(digits)

    if corrupted == phone:
        # Extremely defensive fallback.
        return phone[:-1] + (
            "0"
            if phone[-1] != "0"
            else "1"
        )

    return corrupted


def _corrupt_email(
    email: str,
    rng: np.random.Generator,
) -> str:
    """
    Introduce a plausible typo while usually preserving the domain.
    """
    if "@" not in email:
        return email

    local, domain = email.split("@", maxsplit=1)

    if len(local) < 2:
        return email

    operation = str(
        rng.choice(
            [
                "drop_character",
                "replace_character",
                "swap_characters",
                "duplicate_character",
            ]
        )
    )

    characters = list(local)

    if operation == "drop_character":
        position = int(
            rng.integers(0, len(characters))
        )

        del characters[position]

    elif operation == "replace_character":
        position = int(
            rng.integers(0, len(characters))
        )

        original = characters[position]

        alternatives = [
            char
            for char in string.ascii_lowercase
            if char != original
        ]

        characters[position] = str(
            rng.choice(alternatives)
        )

    elif operation == "swap_characters":
        position = int(
            rng.integers(
                0,
                len(characters) - 1,
            )
        )

        (
            characters[position],
            characters[position + 1],
        ) = (
            characters[position + 1],
            characters[position],
        )

    else:
        position = int(
            rng.integers(0, len(characters))
        )

        characters.insert(
            position,
            characters[position],
        )

    corrupted = (
        "".join(characters)
        + "@"
        + domain
    )

    if corrupted == email:
        return f"{local}x@{domain}"

    return corrupted


def _create_duplicate_variant(
    row: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, Any]:
    """
    Create a non-identical duplicate CRM observation.

    A duplicate represents the same true lead but may have small
    representational differences.
    """
    duplicate = row.copy()

    # Most duplicates receive at least one small identity variation.
    operation = str(
        rng.choice(
            [
                "phone",
                "name",
                "email_case",
            ]
        )
    )

    if (
        operation == "phone"
        and duplicate["phone"] is not None
    ):
        raw_phone = "".join(
            char
            for char in str(duplicate["phone"])
            if char.isdigit()
        )

        if (
            len(raw_phone) == 11
            and raw_phone.startswith("1")
        ):
            raw_phone = raw_phone[1:]

        duplicate["phone"] = _format_phone(
            raw_phone,
            rng,
        )

    elif (
        operation == "name"
        and duplicate["name"] is not None
    ):
        name = str(duplicate["name"])

        duplicate["name"] = str(
            rng.choice(
                [
                    name.upper(),
                    name.lower(),
                    " ".join(name.split()),
                ]
            )
        )

    elif (
        operation == "email_case"
        and duplicate["email"] is not None
    ):
        email = str(duplicate["email"])

        local, separator, domain = (
            email.partition("@")
        )

        duplicate["email"] = (
            local.capitalize()
            + separator
            + domain
        )

    return duplicate


def corrupt_crm_leads(
    leads: pl.DataFrame,
    customers: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Convert clean ground truth into a deliberately imperfect CRM export.

    Returns:
        crm_export:
            Public-facing dirty CRM data.

        corruption_log:
            Ground-truth audit trail of every intentional corruption.

        observation_map:
            Hidden mapping between CRM observations and true lead/customer
            entities. This will later allow objective evaluation of record
            linkage and duplicate detection.
    """
    rng = np.random.default_rng(
        config.seed + 3
    )

    hard_rng = np.random.default_rng(
        config.seed + 30
    )

    customer_lookup = {
        row["customer_id"]: row
        for row in customers.iter_rows(
            named=True
        )
    }

    crm_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []

    crm_record_number = 1
    corruption_number = 1

    def next_crm_id() -> str:
        nonlocal crm_record_number

        crm_record_id = (
            f"CRM{crm_record_number:07d}"
        )

        crm_record_number += 1

        return crm_record_id

    def log_corruption(
        *,
        crm_record_id: str | None,
        lead_id: str,
        field: str,
        corruption_type: str,
        original_value: Any,
        corrupted_value: Any,
    ) -> None:
        nonlocal corruption_number

        log_rows.append(
            {
                "corruption_id": (
                    f"C{corruption_number:07d}"
                ),
                "system": "crm",
                "record_type": "lead",
                "crm_record_id": crm_record_id,
                "ground_truth_lead_id": lead_id,
                "field": field,
                "corruption_type": (
                    corruption_type
                ),
                "original_value": (
                    None
                    if original_value is None
                    else str(original_value)
                ),
                "corrupted_value": (
                    None
                    if corrupted_value is None
                    else str(corrupted_value)
                ),
            }
        )

        corruption_number += 1

    for lead in leads.iter_rows(named=True):
        lead_id = str(lead["lead_id"])
        customer_id = int(
            lead["customer_id"]
        )

        customer = customer_lookup[
            customer_id
        ]

        # ------------------------------------------------------------
        # Lead entirely missing from CRM
        # ------------------------------------------------------------

        if (
            rng.random()
            < config.missing_crm_lead_rate
        ):
            log_corruption(
                crm_record_id=None,
                lead_id=lead_id,
                field="record",
                corruption_type="missing_crm_lead",
                original_value=lead_id,
                corrupted_value=None,
            )

            continue

        crm_record_id = next_crm_id()

        row: dict[str, Any] = {
            "crm_record_id": crm_record_id,
            "created_at": lead["created_at"],
            "name": customer[
                "canonical_name"
            ],
            "email": customer[
                "canonical_email"
            ],
            "phone": customer[
                "canonical_phone"
            ],
            "zip_code": customer[
                "zip_code"
            ],
            "source": lead["source"],
            "campaign": lead["campaign"],
            "service": lead["service"],
            "salesperson_id": lead[
                "salesperson_id"
            ],
            "response_minutes": lead[
                "response_minutes"
            ],
            "qualified": lead[
                "qualified"
            ],
            "estimate_id": lead[
                "estimate_id"
            ],
            "won": lead["won"],
            "funnel_stage": lead[
                "funnel_stage"
            ],
        }

        # ------------------------------------------------------------
        # Phone quality / representation
        # ------------------------------------------------------------

        if row["phone"] is not None:
            phone_draw = rng.random()

            if (
                phone_draw
                < config.missing_phone_rate
            ):
                original = str(
                    row["phone"]
                )

                row["phone"] = None

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="phone",
                    corruption_type="missing_phone",
                    original_value=original,
                    corrupted_value=None,
                )

            elif (
                phone_draw
                < (
                    config.missing_phone_rate
                    + config.malformed_phone_rate
                )
            ):
                original = str(
                    row["phone"]
                )

                corrupted = _corrupt_phone(
                    original,
                    rng,
                )

                row["phone"] = corrupted

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="phone",
                    corruption_type="malformed_phone",
                    original_value=original,
                    corrupted_value=corrupted,
                )

            elif (
                rng.random()
                < config.phone_format_rate
            ):
                original = str(
                    row["phone"]
                )

                formatted = _format_phone(
                    original,
                    rng,
                )

                row["phone"] = formatted

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="phone",
                    corruption_type="phone_format",
                    original_value=original,
                    corrupted_value=formatted,
                )

        # ------------------------------------------------------------
        # Email quality
        # ------------------------------------------------------------

        if row["email"] is not None:
            email_draw = rng.random()

            if (
                email_draw
                < config.missing_email_rate
            ):
                original = str(
                    row["email"]
                )

                row["email"] = None

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="email",
                    corruption_type="missing_email",
                    original_value=original,
                    corrupted_value=None,
                )

            elif (
                email_draw
                < (
                    config.missing_email_rate
                    + config.malformed_email_rate
                )
            ):
                original = str(
                    row["email"]
                )

                corrupted = _corrupt_email(
                    original,
                    rng,
                )

                row["email"] = corrupted

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="email",
                    corruption_type="malformed_email",
                    original_value=original,
                    corrupted_value=corrupted,
                )

        # ------------------------------------------------------------
        # Source quality / representation
        # ------------------------------------------------------------

        if row["source"] is not None:
            source_draw = rng.random()

            if (
                source_draw
                < config.missing_source_rate
            ):
                original = str(
                    row["source"]
                )

                row["source"] = None

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="source",
                    corruption_type="missing_source",
                    original_value=original,
                    corrupted_value=None,
                )

            elif (
                source_draw
                < (
                    config.missing_source_rate
                    + config.source_alias_rate
                )
            ):
                original = str(
                    row["source"]
                )

                aliased = _alias_source(
                    original,
                    rng,
                )

                row["source"] = aliased

                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field="source",
                    corruption_type="source_alias",
                    original_value=original,
                    corrupted_value=aliased,
                )

        if (
            hard_rng.random()
            < config.crm_hard_identity_rate
        ):
            selected_fields: list[str] = []
        
            # Exact email matching must fail.
            if row["email"] is not None:
                selected_fields.append(
                    "email"
                )
        
            # Exact phone matching must fail.
            if row["phone"] is not None:
                selected_fields.append(
                    "phone"
                )
        
            # Break the name + ZIP fallback.
            secondary_fields = [
                field
                for field in [
                    "name",
                    "zip_code",
                ]
                if row[field] is not None
            ]
        
            if secondary_fields:
                selected_fields.append(
                    str(
                        hard_rng.choice(
                            secondary_fields
                        )
                    )
                )
        
            for field in selected_fields:
                original = row[field]
        
                if field == "name":
                    corrupted = _corrupt_name(
                        str(original),
                        hard_rng,
                    )
        
                elif field == "email":
                    corrupted = _corrupt_email(
                        str(original),
                        hard_rng,
                    )
        
                elif field == "phone":
                    corrupted = _corrupt_phone(
                        str(original),
                        hard_rng,
                    )
        
                elif field == "zip_code":
                    corrupted = _corrupt_zip(
                        str(original),
                        hard_rng,
                    )
        
                else:
                    continue
        
                row[field] = corrupted
        
                log_corruption(
                    crm_record_id=crm_record_id,
                    lead_id=lead_id,
                    field=field,
                    corruption_type=(
                        "hard_identity_corruption"
                    ),
                    original_value=original,
                    corrupted_value=corrupted,
                )

        # ------------------------------------------------------------
        # Store original CRM observation
        # ------------------------------------------------------------

        crm_rows.append(row)
        
        mapping_rows.append(
            {
                "crm_record_id": crm_record_id,
                "ground_truth_lead_id": lead_id,
                "ground_truth_customer_id": customer_id,
                "is_duplicate": False,
                "duplicate_of_crm_record_id": None,
            }
        )

        # ------------------------------------------------------------
        # Duplicate CRM observation
        # ------------------------------------------------------------

        if (
            rng.random()
            < config.duplicate_rate
        ):
            duplicate_id = next_crm_id()

            duplicate = (
                _create_duplicate_variant(
                    row,
                    rng,
                )
            )

            duplicate[
                "crm_record_id"
            ] = duplicate_id

            crm_rows.append(
                duplicate
            )

            mapping_rows.append(
                {
                    "crm_record_id": (
                        duplicate_id
                    ),
                    "ground_truth_lead_id": (
                        lead_id
                    ),
                    "ground_truth_customer_id": (
                        customer_id
                    ),
                    "is_duplicate": True,
                    "duplicate_of_crm_record_id": (
                        crm_record_id
                    ),
                }
            )

            log_corruption(
                crm_record_id=duplicate_id,
                lead_id=lead_id,
                field="record",
                corruption_type=(
                    "duplicate_record"
                ),
                original_value=crm_record_id,
                corrupted_value=duplicate_id,
            )

    crm_export = pl.DataFrame(
        crm_rows
    ).select(CRM_COLUMNS)

    corruption_log = pl.DataFrame(
        log_rows
    )

    observation_map = pl.DataFrame(
        mapping_rows
    )

    return (
        crm_export,
        corruption_log,
        observation_map,
    )
