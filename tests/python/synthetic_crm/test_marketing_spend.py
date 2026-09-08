import polars as pl

from synthetic_crm.config import (
    SimulationConfig,
)
from synthetic_crm.customers import (
    generate_customers,
)
from synthetic_crm.funnel import (
    generate_funnel,
)
from synthetic_crm.marketing import (
    generate_leads,
)
from synthetic_crm.marketing_spend import (
    PAID_CAMPAIGNS,
    generate_marketing_spend,
)


def _generate_test_data():
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(
        config
    )

    base_leads = generate_leads(
        customers,
        config,
    )

    _, leads, _, _ = generate_funnel(
        base_leads,
        customers,
        config,
    )

    return config, leads


def test_marketing_spend_keys_are_unique() -> None:
    config, leads = (
        _generate_test_data()
    )

    spend, _ = (
        generate_marketing_spend(
            leads,
            config,
        )
    )

    assert (
        spend
        .select(
            "date",
            "platform",
            "campaign",
        )
        .unique()
        .height
        == spend.height
    )


def test_marketing_spend_is_nonnegative() -> None:
    config, leads = (
        _generate_test_data()
    )

    spend, _ = (
        generate_marketing_spend(
            leads,
            config,
        )
    )

    assert (
        spend
        .filter(
            pl.col("spend") < 0
        )
        .height
        == 0
    )

    assert (
        spend
        .filter(
            pl.col("clicks") < 0
        )
        .height
        == 0
    )

    assert (
        spend
        .filter(
            pl.col("impressions")
            < pl.col("clicks")
        )
        .height
        == 0
    )


def test_truth_recovers_all_paid_leads() -> None:
    config, leads = (
        _generate_test_data()
    )

    _, truth = (
        generate_marketing_spend(
            leads,
            config,
        )
    )

    paid_sources = list(
        PAID_CAMPAIGNS
    )

    expected = (
        leads
        .filter(
            pl.col("source")
            .is_in(
                paid_sources
            )
        )
        .height
    )

    observed = int(
        truth[
            "ground_truth_leads"
        ].sum()
    )

    assert observed == expected


def test_reporting_gap_is_consistent() -> None:
    config, leads = (
        _generate_test_data()
    )

    _, truth = (
        generate_marketing_spend(
            leads,
            config,
        )
    )

    incorrect = truth.filter(
        pl.col(
            "conversion_reporting_gap"
        )
        != (
            pl.col(
                "platform_conversions"
            )
            - pl.col(
                "ground_truth_leads"
            )
        )
    )

    assert incorrect.height == 0


def test_marketing_spend_is_reproducible() -> None:
    config, leads = (
        _generate_test_data()
    )

    first = generate_marketing_spend(
        leads,
        config,
    )

    second = generate_marketing_spend(
        leads,
        config,
    )

    for first_df, second_df in zip(
        first,
        second,
        strict=True,
    ):
        assert first_df.equals(
            second_df
        )
