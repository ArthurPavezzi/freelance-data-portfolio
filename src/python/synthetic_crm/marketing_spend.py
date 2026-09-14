from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import polars as pl

from .config import SimulationConfig

PAID_CAMPAIGNS = {
    "Google Ads": {
        "Search | Interior Painting": {
            "target_cpl": 95.0,
            "cpc": 7.00,
            "ctr": 0.065,
            "active_months": None,
        },
        "Search | Exterior Painting": {
            "target_cpl": 110.0,
            "cpc": 8.00,
            "ctr": 0.060,
            "active_months": None,
        },
        "Search | Cabinet Painting": {
            "target_cpl": 90.0,
            "cpc": 6.50,
            "ctr": 0.067,
            "active_months": None,
        },
        "Search | Drywall Repair": {
            "target_cpl": 75.0,
            "cpc": 5.50,
            "ctr": 0.070,
            "active_months": None,
        },
        "Search | Minor Remodeling": {
            "target_cpl": 135.0,
            "cpc": 9.50,
            "ctr": 0.055,
            "active_months": None,
        },
    },
    "Facebook Ads": {
        "Meta | Home Refresh": {
            "target_cpl": 70.0,
            "cpc": 2.80,
            "ctr": 0.017,
            "active_months": None,
        },
        "Meta | Seasonal Promo": {
            "target_cpl": 62.0,
            "cpc": 2.40,
            "ctr": 0.019,
            "active_months": {
                3,
                4,
                5,
                6,
                9,
                10,
            },
        },
        "Meta | Free Estimate": {
            "target_cpl": 58.0,
            "cpc": 2.10,
            "ctr": 0.021,
            "active_months": None,
        },
    },
}


PLATFORM_BY_SOURCE = {
    "Google Ads": "Google Ads",
    "Facebook Ads": "Meta",
}


ATTRIBUTION_PARAMETERS = {
    "Google Ads": {
        "capture_probability": 0.975,
        "modeled_conversion_rate": 0.055,
        "phantom_conversion_lambda": 0.015,
    },
    "Facebook Ads": {
        "capture_probability": 0.940,
        "modeled_conversion_rate": 0.120,
        "phantom_conversion_lambda": 0.025,
    },
}


SPEND_COLUMNS = [
    "date",
    "platform",
    "source",
    "campaign",
    "spend",
    "impressions",
    "clicks",
    "platform_conversions",
]


TRUTH_COLUMNS = [
    "date",
    "platform",
    "source",
    "campaign",
    "ground_truth_leads",
    "platform_conversions",
    "conversion_reporting_gap",
]


def _date_range(
    start_date: str,
    end_date: str,
) -> list[date]:
    start = datetime.fromisoformat(start_date).date()

    end = datetime.fromisoformat(end_date).date()

    dates: list[date] = []

    current = start

    while current <= end:
        dates.append(current)
        current += timedelta(days=1)

    return dates


def _count_true_paid_leads(
    leads: pl.DataFrame,
) -> dict[
    tuple[date, str, str],
    int,
]:
    """
    Count true paid leads by day, source, and campaign.
    """
    paid_sources = list(PAID_CAMPAIGNS)

    counts = (
        leads.filter(pl.col("source").is_in(paid_sources))
        .with_columns(pl.col("created_at").dt.date().alias("date"))
        .group_by(
            "date",
            "source",
            "campaign",
        )
        .len()
    )

    return {
        (
            row["date"],
            row["source"],
            row["campaign"],
        ): int(row["len"])
        for row in counts.iter_rows(named=True)
    }


def _sample_platform_conversions(
    true_leads: int,
    source: str,
    rng: np.random.Generator,
) -> int:
    """
    Simulate platform-reported conversions.

    Platforms may fail to observe some real conversions while also
    reporting modeled, attributed, or occasional phantom conversions.
    """
    params = ATTRIBUTION_PARAMETERS[source]

    captured = int(
        rng.binomial(
            true_leads,
            params["capture_probability"],
        )
    )

    modeled = int(rng.poisson(true_leads * params["modeled_conversion_rate"]))

    phantom = int(rng.poisson(params["phantom_conversion_lambda"]))

    return captured + modeled + phantom


def _sample_spend(
    true_leads: int,
    target_cpl: float,
    rng: np.random.Generator,
) -> float:
    """
    Generate daily campaign spend.

    Spend is economically related to observed demand but remains noisy.
    A small latent-demand component keeps campaigns spending on days
    when no lead happens to convert.
    """
    latent_demand = true_leads + rng.gamma(
        shape=1.4,
        scale=0.25,
    )

    noise = rng.lognormal(
        mean=0.0,
        sigma=0.18,
    )

    spend = target_cpl * latent_demand * noise

    return round(
        max(spend, 5.0),
        2,
    )


def _sample_clicks(
    spend: float,
    baseline_cpc: float,
    rng: np.random.Generator,
) -> int:
    realized_cpc = baseline_cpc * rng.lognormal(
        mean=0.0,
        sigma=0.10,
    )

    clicks = round(spend / realized_cpc)

    return max(
        int(clicks),
        1,
    )


def _sample_impressions(
    clicks: int,
    baseline_ctr: float,
    rng: np.random.Generator,
) -> int:
    realized_ctr = baseline_ctr * rng.lognormal(
        mean=0.0,
        sigma=0.08,
    )

    realized_ctr = float(
        np.clip(
            realized_ctr,
            0.005,
            0.15,
        )
    )

    impressions = round(clicks / realized_ctr)

    return max(
        int(impressions),
        clicks,
    )


def generate_marketing_spend(
    leads: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Generate daily paid-marketing performance reports.

    The public export contains platform-reported metrics.

    The hidden truth table preserves the number of actual paid leads
    associated with each campaign-day so reporting discrepancies can
    later be evaluated objectively.
    """
    rng = np.random.default_rng(config.seed + 5)

    true_lead_counts = _count_true_paid_leads(leads)

    spend_rows: list[dict[str, Any]] = []

    truth_rows: list[dict[str, Any]] = []

    for current_date in _date_range(
        config.start_date,
        config.end_date,
    ):
        for (
            source,
            campaigns,
        ) in PAID_CAMPAIGNS.items():
            platform = PLATFORM_BY_SOURCE[source]

            for (
                campaign,
                parameters,
            ) in campaigns.items():
                active_months = parameters.get("active_months")

                if active_months is not None and current_date.month not in active_months:
                    continue

                true_leads = true_lead_counts.get(
                    (
                        current_date,
                        source,
                        campaign,
                    ),
                    0,
                )

                platform_conversions = _sample_platform_conversions(
                    true_leads,
                    source,
                    rng,
                )

                spend = _sample_spend(
                    true_leads,
                    float(parameters["target_cpl"]),
                    rng,
                )

                clicks = _sample_clicks(
                    spend,
                    float(parameters["cpc"]),
                    rng,
                )

                impressions = _sample_impressions(
                    clicks,
                    float(parameters["ctr"]),
                    rng,
                )

                spend_rows.append(
                    {
                        "date": (current_date),
                        "platform": (platform),
                        "source": source,
                        "campaign": (campaign),
                        "spend": spend,
                        "impressions": (impressions),
                        "clicks": clicks,
                        "platform_conversions": (platform_conversions),
                    }
                )

                truth_rows.append(
                    {
                        "date": (current_date),
                        "platform": (platform),
                        "source": source,
                        "campaign": (campaign),
                        "ground_truth_leads": (true_leads),
                        "platform_conversions": (platform_conversions),
                        "conversion_reporting_gap": (platform_conversions - true_leads),
                    }
                )

    spend_export = pl.DataFrame(spend_rows).select(SPEND_COLUMNS)

    spend_truth = pl.DataFrame(truth_rows).select(TRUTH_COLUMNS)

    return (
        spend_export,
        spend_truth,
    )
