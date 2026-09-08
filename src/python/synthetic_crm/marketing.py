from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl

from .config import SimulationConfig


FIRST_LEAD_SOURCES = {
    "Google Ads": 0.32,
    "Facebook Ads": 0.18,
    "Organic Search": 0.17,
    "Referral": 0.14,
    "Partner": 0.10,
    "Direct": 0.09,
}

REPEAT_LEAD_SOURCES = {
    "Google Ads": 0.18,
    "Facebook Ads": 0.08,
    "Organic Search": 0.20,
    "Referral": 0.20,
    "Partner": 0.08,
    "Direct": 0.26,
}

SERVICES = {
    "Interior Painting": 0.30,
    "Exterior Painting": 0.27,
    "Cabinet Painting": 0.16,
    "Drywall Repair": 0.15,
    "Minor Remodeling": 0.12,
}

MONTH_WEIGHTS = {
    1: 0.75,
    2: 0.85,
    3: 1.10,
    4: 1.25,
    5: 1.35,
    6: 1.25,
    7: 1.05,
    8: 1.00,
    9: 0.95,
    10: 1.05,
    11: 0.85,
    12: 0.65,
}

WEEKDAY_WEIGHTS = {
    0: 1.00,  # Monday
    1: 1.00,  # Tuesday
    2: 1.00,  # Wednesday
    3: 1.00,  # Thursday
    4: 0.90,  # Friday
    5: 0.65,  # Saturday
    6: 0.45,  # Sunday
}


def _hour_weight(hour: int) -> float:
    """Return relative probability of a lead arriving during an hour."""
    if 0 <= hour < 7:
        return 0.25

    if 7 <= hour < 9:
        return 0.70

    if 9 <= hour < 18:
        return 1.00

    if 18 <= hour < 21:
        return 0.80

    return 0.40


def _build_timestamp_pool(
    start_date: str,
    end_date: str,
) -> tuple[list[datetime], np.ndarray]:
    """
    Build an hourly timestamp pool for first leads.

    Sampling weights introduce seasonality by month, weekday, and hour.
    """
    start = datetime.fromisoformat(start_date)

    # Add one day so the entire end_date is included.
    end = datetime.fromisoformat(end_date) + timedelta(days=1)

    timestamps: list[datetime] = []
    weights: list[float] = []

    current = start

    while current < end:
        weight = (
            MONTH_WEIGHTS[current.month]
            * WEEKDAY_WEIGHTS[current.weekday()]
            * _hour_weight(current.hour)
        )

        timestamps.append(current)
        weights.append(weight)

        current += timedelta(hours=1)

    probabilities = np.asarray(weights, dtype=float)
    probabilities /= probabilities.sum()

    return timestamps, probabilities


def _sample_source(
    rng: np.random.Generator,
    *,
    repeat_lead: bool,
) -> str:
    """Sample an acquisition source conditional on lead type."""
    probabilities = (
        REPEAT_LEAD_SOURCES
        if repeat_lead
        else FIRST_LEAD_SOURCES
    )

    return str(
        rng.choice(
            list(probabilities),
            p=list(probabilities.values()),
        )
    )


def _sample_service(
    rng: np.random.Generator,
) -> str:
    """Sample the service requested by the lead."""
    return str(
        rng.choice(
            list(SERVICES),
            p=list(SERVICES.values()),
        )
    )


def _sample_repeat_gap(
    rng: np.random.Generator,
) -> timedelta:
    """
    Sample the time between genuine customer inquiries.

    Genuine repeat leads must occur at least 14 days after the previous
    inquiry. Additional waiting time follows a Gamma distribution,
    producing a right-skewed pattern with most returns occurring after
    several weeks or months.
    """
    minimum_days = 14

    additional_days = rng.gamma(
        shape=2.2,
        scale=55.0,
    )

    return timedelta(
        days=minimum_days + float(additional_days)
    )


def _campaign_for_source(
    source: str,
    service: str,
    rng: np.random.Generator,
) -> str:
    """Generate a plausible marketing campaign label."""
    if source == "Google Ads":
        return f"Search | {service}"

    if source == "Facebook Ads":
        return str(
            rng.choice(
                [
                    "Meta | Home Refresh",
                    "Meta | Seasonal Promo",
                    "Meta | Free Estimate",
                ]
            )
        )

    if source == "Partner":
        return str(
            rng.choice(
                [
                    "Realtor Network",
                    "Property Manager",
                    "Local Contractor",
                ]
            )
        )

    if source == "Referral":
        return "Customer Referral"

    if source == "Organic Search":
        return "Organic Search"

    return "Direct"


def _generate_customer_timestamps(
    lead_count: int,
    timestamps: list[datetime],
    timestamp_probs: np.ndarray,
    simulation_end: datetime,
    rng: np.random.Generator,
) -> list[datetime]:
    """
    Generate chronologically valid lead timestamps for one customer.

    The first lead follows the overall seasonal arrival process.
    Genuine repeat leads occur sequentially after the previous lead
    with a minimum gap of 14 days.

    Repeat events falling outside the observation window are censored.
    """
    first_index = int(
        rng.choice(
            len(timestamps),
            p=timestamp_probs,
        )
    )

    first_timestamp = (
        timestamps[first_index]
        + timedelta(
            minutes=int(rng.integers(0, 60))
        )
    )

    customer_timestamps = [first_timestamp]

    for _ in range(1, lead_count):
        next_timestamp = (
            customer_timestamps[-1]
            + _sample_repeat_gap(rng)
        )

        if next_timestamp > simulation_end:
            break

        customer_timestamps.append(next_timestamp)

    return customer_timestamps


def generate_leads(
    customers: pl.DataFrame,
    config: SimulationConfig,
) -> pl.DataFrame:
    """
    Generate synthetic CRM lead events.

    Every customer has at least one lead. Additional potential leads
    follow a Poisson process calibrated to approximately reach
    config.target_leads.

    Some potential repeat leads are naturally right-censored when their
    simulated timestamp falls outside the observation period.
    """
    # Use a different deterministic random stream from customer generation.
    rng = np.random.default_rng(config.seed + 1)

    customer_ids = customers["customer_id"].to_numpy()

    if config.target_leads < len(customer_ids):
        raise ValueError(
            "target_leads must be greater than or equal to "
            "target_customers."
        )

    expected_extra_leads = (
        (config.target_leads - len(customer_ids))
        / len(customer_ids)
        * config.lead_censoring_adjustment
    )
    
    extra_leads = rng.poisson(
        lam=expected_extra_leads,
        size=len(customer_ids),
    )

    potential_lead_counts = 1 + extra_leads

    timestamps, timestamp_probs = _build_timestamp_pool(
        config.start_date,
        config.end_date,
    )

    simulation_end = (
        datetime.fromisoformat(config.end_date)
        + timedelta(
            hours=23,
            minutes=59,
            seconds=59,
        )
    )

    rows: list[dict[str, object]] = []
    lead_number = 1

    for customer_id, potential_lead_count in zip(
        customer_ids,
        potential_lead_counts,
        strict=True,
    ):
        customer_timestamps = _generate_customer_timestamps(
            lead_count=int(potential_lead_count),
            timestamps=timestamps,
            timestamp_probs=timestamp_probs,
            simulation_end=simulation_end,
            rng=rng,
        )

        for sequence, created_at in enumerate(
            customer_timestamps,
            start=1,
        ):
            repeat_lead = sequence > 1

            source = _sample_source(
                rng,
                repeat_lead=repeat_lead,
            )

            service = _sample_service(rng)

            campaign = _campaign_for_source(
                source,
                service,
                rng,
            )

            rows.append(
                {
                    "lead_id": f"L{lead_number:07d}",
                    "customer_id": int(customer_id),
                    "lead_sequence": sequence,
                    "created_at": created_at,
                    "source": source,
                    "campaign": campaign,
                    "service": service,
                }
            )

            lead_number += 1

    return pl.DataFrame(rows)
