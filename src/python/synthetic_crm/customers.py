from faker import Faker
import numpy as np
import polars as pl

from .config import SimulationConfig


def generate_customers(config: SimulationConfig) -> pl.DataFrame:
    fake = Faker("en_US")
    Faker.seed(config.seed)

    rng = np.random.default_rng(config.seed)

    rows = []

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
                "canonical_email": fake.unique.email(),
                "canonical_phone": fake.unique.numerify("210#######"),
                "zip_code": rng.choice(zip_codes),
            }
        )

    return pl.DataFrame(rows)
