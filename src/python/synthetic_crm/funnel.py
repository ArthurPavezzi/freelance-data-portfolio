from __future__ import annotations

from datetime import datetime, timedelta
from math import exp, log

import numpy as np
import polars as pl

from .config import SimulationConfig


SALESPERSONS = {
    "S001": {
        "name": "Alex Morgan",
        "assignment_weight": 0.30,
        "response_multiplier": 0.85,
        "close_bonus": 0.35,
    },
    "S002": {
        "name": "Jordan Lee",
        "assignment_weight": 0.27,
        "response_multiplier": 1.00,
        "close_bonus": 0.10,
    },
    "S003": {
        "name": "Taylor Brooks",
        "assignment_weight": 0.23,
        "response_multiplier": 1.15,
        "close_bonus": -0.10,
    },
    "S004": {
        "name": "Casey Rivera",
        "assignment_weight": 0.20,
        "response_multiplier": 0.95,
        "close_bonus": 0.20,
    },
}

SOURCE_RESPONSE_MEDIANS = {
    "Google Ads": 30.0,
    "Facebook Ads": 45.0,
    "Organic Search": 35.0,
    "Referral": 20.0,
    "Partner": 25.0,
    "Direct": 25.0,
}

SOURCE_QUALIFICATION_EFFECTS = {
    "Google Ads": 0.15,
    "Facebook Ads": -0.45,
    "Organic Search": 0.30,
    "Referral": 0.90,
    "Partner": 0.55,
    "Direct": 0.40,
}

SOURCE_WIN_EFFECTS = {
    "Google Ads": 0.05,
    "Facebook Ads": -0.45,
    "Organic Search": 0.25,
    "Referral": 0.90,
    "Partner": 0.55,
    "Direct": 0.35,
}

SERVICE_QUALIFICATION_EFFECTS = {
    "Interior Painting": 0.10,
    "Exterior Painting": 0.15,
    "Cabinet Painting": 0.05,
    "Drywall Repair": -0.20,
    "Minor Remodeling": 0.30,
}

SERVICE_MEDIAN_ESTIMATES = {
    "Interior Painting": 4_200.0,
    "Exterior Painting": 6_200.0,
    "Cabinet Painting": 3_400.0,
    "Drywall Repair": 1_400.0,
    "Minor Remodeling": 9_500.0,
}

SERVICE_JOB_DURATION_DAYS = {
    "Interior Painting": 3,
    "Exterior Painting": 4,
    "Cabinet Painting": 4,
    "Drywall Repair": 2,
    "Minor Remodeling": 8,
}

ZIP_VALUE_MULTIPLIERS = {
    "78201": 0.92,
    "78209": 1.20,
    "78213": 0.95,
    "78216": 1.02,
    "78217": 0.96,
    "78228": 0.90,
    "78229": 1.00,
    "78230": 1.12,
    "78232": 1.08,
    "78240": 0.98,
}


def _sigmoid(value: float) -> float:
    """Convert a latent score into a probability."""
    value = max(min(value, 30.0), -30.0)
    return 1.0 / (1.0 + exp(-value))


def _generate_salespeople() -> pl.DataFrame:
    """Return the salesperson ground-truth table."""
    rows = []

    for salesperson_id, attributes in SALESPERSONS.items():
        rows.append(
            {
                "salesperson_id": salesperson_id,
                "salesperson_name": attributes["name"],
                "assignment_weight": attributes["assignment_weight"],
                "response_multiplier": attributes[
                    "response_multiplier"
                ],
                "close_bonus": attributes["close_bonus"],
            }
        )

    return pl.DataFrame(rows)


def _sample_salesperson(
    rng: np.random.Generator,
) -> str:
    salesperson_ids = list(SALESPERSONS)

    probabilities = [
        float(SALESPERSONS[salesperson_id]["assignment_weight"])
        for salesperson_id in salesperson_ids
    ]

    return str(
        rng.choice(
            salesperson_ids,
            p=probabilities,
        )
    )


def _after_hours_multiplier(
    created_at: datetime,
) -> float:
    """
    Increase response time outside normal business hours.

    Weekend and after-hours leads remain valid but tend to receive
    slower responses.
    """
    multiplier = 1.0

    if created_at.weekday() >= 5:
        multiplier *= 1.30

    if created_at.hour < 8 or created_at.hour >= 18:
        multiplier *= 2.00

    return multiplier


def _sample_response_minutes(
    source: str,
    salesperson_id: str,
    created_at: datetime,
    rng: np.random.Generator,
) -> int:
    """
    Generate a right-skewed response time.

    Source, salesperson speed, and arrival time all affect response.
    """
    median = SOURCE_RESPONSE_MEDIANS[source]

    salesperson_multiplier = float(
        SALESPERSONS[salesperson_id]["response_multiplier"]
    )

    median *= salesperson_multiplier
    median *= _after_hours_multiplier(created_at)

    response = rng.lognormal(
        mean=log(median),
        sigma=0.80,
    )

    return int(
        np.clip(
            round(response),
            2,
            4_320,
        )
    )


def _qualification_probability(
    source: str,
    service: str,
    response_minutes: int,
    repeat_lead: bool,
) -> float:
    """
    Probability that a lead is commercially qualified.

    Referrals, repeat customers, and stronger-intent sources tend to
    qualify more often. Very slow responses reduce qualification.
    """
    score = 0.45

    score += SOURCE_QUALIFICATION_EFFECTS[source]
    score += SERVICE_QUALIFICATION_EFFECTS[service]

    if repeat_lead:
        score += 0.60

    score -= 0.25 * log(
        1.0 + response_minutes / 30.0
    )

    return _sigmoid(score)


def _estimate_probability(
    response_minutes: int,
    repeat_lead: bool,
) -> float:
    """
    Probability that a qualified lead progresses to an estimate.
    """
    score = 1.65

    if repeat_lead:
        score += 0.25

    score -= 0.20 * log(
        1.0 + response_minutes / 60.0
    )

    return _sigmoid(score)


def _sample_estimate_value(
    service: str,
    zip_code: str,
    rng: np.random.Generator,
) -> float:
    """
    Generate a positive, right-skewed project estimate.

    Service type determines the baseline price, while ZIP code applies
    a modest market-value multiplier.
    """
    median = SERVICE_MEDIAN_ESTIMATES[service]

    zip_multiplier = ZIP_VALUE_MULTIPLIERS.get(
        zip_code,
        1.0,
    )

    value = rng.lognormal(
        mean=log(median * zip_multiplier),
        sigma=0.35,
    )

    return round(
        max(value, 250.0),
        2,
    )


def _win_probability(
    source: str,
    salesperson_id: str,
    service: str,
    estimate_value: float,
    response_minutes: int,
    repeat_lead: bool,
) -> float:
    """
    Probability that an estimate becomes a booked job.
    """
    service_baseline = SERVICE_MEDIAN_ESTIMATES[service]

    relative_price = (
        estimate_value / service_baseline
    )

    score = -0.55

    score += SOURCE_WIN_EFFECTS[source]

    score += float(
        SALESPERSONS[salesperson_id]["close_bonus"]
    )

    if repeat_lead:
        score += 0.65

    score -= 0.30 * log(
        1.0 + response_minutes / 60.0
    )

    score -= 0.80 * log(relative_price)

    return _sigmoid(score)


def _sample_estimate_timestamp(
    created_at: datetime,
    response_minutes: int,
    rng: np.random.Generator,
) -> datetime:
    """
    Generate the time at which an estimate is formally created.
    """
    initial_contact = (
        created_at
        + timedelta(minutes=response_minutes)
    )

    additional_days = rng.gamma(
        shape=1.5,
        scale=1.2,
    )

    return (
        initial_contact
        + timedelta(days=float(additional_days))
    )


def _sample_job_schedule(
    estimate_created_at: datetime,
    rng: np.random.Generator,
) -> datetime:
    """
    Generate the scheduled job start after a won estimate.
    """
    wait_days = (
        2.0
        + rng.gamma(
            shape=2.0,
            scale=3.5,
        )
    )

    return (
        estimate_created_at
        + timedelta(days=float(wait_days))
    )


def generate_funnel(
    leads: pl.DataFrame,
    customers: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Simulate the commercial funnel from lead to completed job.

    Returns:
        salespeople
        enriched leads
        estimates
        jobs
    """
    rng = np.random.default_rng(config.seed + 2)

    simulation_end = (
        datetime.fromisoformat(config.end_date)
        + timedelta(
            hours=23,
            minutes=59,
            seconds=59,
        )
    )

    customer_zip_lookup = dict(
        zip(
            customers["customer_id"].to_list(),
            customers["zip_code"].to_list(),
            strict=True,
        )
    )

    salesperson_table = _generate_salespeople()

    lead_rows: list[dict[str, object]] = []
    estimate_rows: list[dict[str, object]] = []
    job_rows: list[dict[str, object]] = []

    estimate_number = 1
    job_number = 1

    for lead in leads.iter_rows(named=True):
        lead_id = str(lead["lead_id"])
        customer_id = int(lead["customer_id"])
        created_at = lead["created_at"]
        source = str(lead["source"])
        service = str(lead["service"])

        repeat_lead = int(lead["lead_sequence"]) > 1

        zip_code = customer_zip_lookup[customer_id]

        salesperson_id = _sample_salesperson(rng)

        response_minutes = _sample_response_minutes(
            source=source,
            salesperson_id=salesperson_id,
            created_at=created_at,
            rng=rng,
        )

        qualification_probability = (
            _qualification_probability(
                source=source,
                service=service,
                response_minutes=response_minutes,
                repeat_lead=repeat_lead,
            )
        )

        qualified = (
            rng.random()
            < qualification_probability
        )

        funnel_stage = "Unqualified"
        estimate_id: str | None = None
        won = False

        if qualified:
            funnel_stage = "Qualified - No Estimate"

            estimate_probability = (
                _estimate_probability(
                    response_minutes=response_minutes,
                    repeat_lead=repeat_lead,
                )
            )

            estimate_created = (
                rng.random()
                < estimate_probability
            )

            if estimate_created:
                estimate_created_at = (
                    _sample_estimate_timestamp(
                        created_at=created_at,
                        response_minutes=response_minutes,
                        rng=rng,
                    )
                )

                # Estimates outside the observation window are censored.
                if estimate_created_at > simulation_end:
                    funnel_stage = "Qualified - Pending"

                else:
                    estimate_id = (
                        f"E{estimate_number:07d}"
                    )
                    estimate_number += 1

                    estimate_value = (
                        _sample_estimate_value(
                            service=service,
                            zip_code=zip_code,
                            rng=rng,
                        )
                    )

                    win_probability = (
                        _win_probability(
                            source=source,
                            salesperson_id=salesperson_id,
                            service=service,
                            estimate_value=estimate_value,
                            response_minutes=response_minutes,
                            repeat_lead=repeat_lead,
                        )
                    )

                    won = (
                        rng.random()
                        < win_probability
                    )

                    estimate_status = (
                        "Won"
                        if won
                        else "Lost"
                    )

                    funnel_stage = (
                        "Won"
                        if won
                        else "Estimate Lost"
                    )

                    estimate_rows.append(
                        {
                            "estimate_id": estimate_id,
                            "lead_id": lead_id,
                            "customer_id": customer_id,
                            "salesperson_id": salesperson_id,
                            "service": service,
                            "estimate_created_at": (
                                estimate_created_at
                            ),
                            "estimate_value": (
                                estimate_value
                            ),
                            "status": estimate_status,
                            "win_probability": (
                                win_probability
                            ),
                        }
                    )

                    if won:
                        scheduled_at = (
                            _sample_job_schedule(
                                estimate_created_at,
                                rng,
                            )
                        )

                        duration_days = (
                            SERVICE_JOB_DURATION_DAYS[
                                service
                            ]
                        )

                        completed_at = (
                            scheduled_at
                            + timedelta(
                                days=duration_days
                            )
                        )

                        if scheduled_at > simulation_end:
                            job_status = "Booked"
                            observed_completed_at = None
                            revenue = 0.0

                        elif completed_at > simulation_end:
                            job_status = "In Progress"
                            observed_completed_at = None
                            revenue = 0.0

                        else:
                            job_status = "Completed"
                            observed_completed_at = (
                                completed_at
                            )
                            revenue = estimate_value

                        job_id = (
                            f"J{job_number:07d}"
                        )
                        job_number += 1

                        job_rows.append(
                            {
                                "job_id": job_id,
                                "estimate_id": estimate_id,
                                "lead_id": lead_id,
                                "customer_id": customer_id,
                                "salesperson_id": salesperson_id,
                                "service": service,
                                "scheduled_at": scheduled_at,
                                "completed_at": (
                                    observed_completed_at
                                ),
                                "contract_value": (
                                    estimate_value
                                ),
                                "revenue": revenue,
                                "status": job_status,
                            }
                        )

        lead_rows.append(
            {
                **lead,
                "zip_code": zip_code,
                "salesperson_id": salesperson_id,
                "response_minutes": response_minutes,
                "qualification_probability": (
                    qualification_probability
                ),
                "qualified": qualified,
                "estimate_id": estimate_id,
                "won": won,
                "funnel_stage": funnel_stage,
            }
        )

    enriched_leads = pl.DataFrame(lead_rows)
    estimates = pl.DataFrame(estimate_rows)
    jobs = pl.DataFrame(job_rows)

    return (
        salesperson_table,
        enriched_leads,
        estimates,
        jobs,
    )
