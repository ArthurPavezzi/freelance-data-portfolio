import re
import unicodedata

import numpy as np
import polars as pl
from faker import Faker

from .config import SimulationConfig


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    return re.sub(r"[^a-z0-9]", "", value)


def _generate_email(
    first_name: str,
    last_name: str,
    customer_id: int,
    rng: np.random.Generator,
    used_emails: set[str],
) -> str:
    first = _slugify(first_name)
    last = _slugify(last_name)

    patterns = [
        f"{first}.{last}",
        f"{first}{last}",
        f"{first[0]}{last}",
        f"{first}.{last}{rng.integers(1, 100)}",
    ]

    domains = [
        "example.com",
        "example.net",
        "example.org",
    ]

    local_part = str(rng.choice(patterns))
    domain = str(rng.choice(domains))

    email = f"{local_part}@{domain}"

    if email in used_emails:
        email = f"{first}.{last}{customer_id}@{domain}"

    used_emails.add(email)
    return email


def _generate_phone(
    rng: np.random.Generator,
    used_phones: set[str],
) -> str:
    while True:
        area_code = str(rng.choice(["210", "726"]))

        exchange = (
            f"{rng.integers(2, 10)}"
            f"{rng.integers(0, 10)}"
            f"{rng.integers(0, 10)}"
        )

        subscriber = f"{rng.integers(0, 10_000):04d}"

        phone = f"{area_code}{exchange}{subscriber}"

        if phone not in used_phones:
            used_phones.add(phone)
            return phone


def generate_customers(config: SimulationConfig) -> pl.DataFrame:
    fake = Faker("en_US")
    Faker.seed(config.seed)

    rng = np.random.default_rng(config.seed)

    rows = []
    used_emails: set[str] = set()
    used_phones: set[str] = set()

    zip_codes = [
        "78201",
        "78209",
        "78213",
        "78216",
        "78217",
        "78228",
        "78229",
        "78230",
        "78232",
        "78240",
    ]

    for customer_id in range(1, config.target_customers + 1):
        first_name = fake.first_name()
        last_name = fake.last_name()

        rows.append(
            {
                "customer_id": customer_id,
                "first_name": first_name,
                "last_name": last_name,
                "canonical_name": f"{first_name} {last_name}",
                "canonical_email": _generate_email(
                    first_name,
                    last_name,
                    customer_id,
                    rng,
                    used_emails,
                ),
                "canonical_phone": _generate_phone(
                    rng,
                    used_phones,
                ),
                "zip_code": str(rng.choice(zip_codes)),
            }
        )

    return pl.DataFrame(rows)
