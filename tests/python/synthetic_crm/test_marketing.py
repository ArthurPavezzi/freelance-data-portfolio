from datetime import timedelta

import polars as pl
from synthetic_crm.config import SimulationConfig
from synthetic_crm.customers import generate_customers
from synthetic_crm.marketing import generate_leads


def test_lead_generation() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)
    leads = generate_leads(customers, config)

    assert leads["lead_id"].n_unique() == leads.height
    assert leads["customer_id"].n_unique() == 500

    assert leads["created_at"].min().date().isoformat() >= config.start_date

    assert leads["created_at"].max().date().isoformat() <= config.end_date


def test_genuine_repeat_leads_are_separated() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)
    leads = generate_leads(customers, config)

    repeat_gaps = (
        leads.sort(["customer_id", "created_at"])
        .with_columns(pl.col("created_at").diff().over("customer_id").alias("gap"))
        .filter(pl.col("lead_sequence") > 1)
    )

    if repeat_gaps.height > 0:
        assert repeat_gaps["gap"].min() >= timedelta(days=14)


def test_lead_timestamps_have_minute_precision() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)
    leads = generate_leads(customers, config)

    assert leads.filter(pl.col("created_at").dt.second() != 0).height == 0

    assert leads.filter(pl.col("created_at").dt.microsecond() != 0).height == 0
