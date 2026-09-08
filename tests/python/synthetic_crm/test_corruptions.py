import polars as pl

from synthetic_crm.config import (
    SimulationConfig,
)
from synthetic_crm.corruptions import (
    corrupt_crm_leads,
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

    return (
        config,
        customers,
        leads,
    )


def test_raw_crm_hides_ground_truth_ids() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    crm, _, _ = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    assert "lead_id" not in crm.columns
    assert "customer_id" not in crm.columns

    assert (
        "crm_record_id"
        in crm.columns
    )


def test_crm_record_ids_are_unique() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    crm, _, _ = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    assert (
        crm["crm_record_id"].n_unique()
        == crm.height
    )


def test_observation_map_covers_all_crm_records() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    crm, _, observation_map = (
        corrupt_crm_leads(
            leads,
            customers,
            config,
        )
    )

    assert (
        observation_map.height
        == crm.height
    )

    assert set(
        observation_map[
            "crm_record_id"
        ].to_list()
    ) == set(
        crm[
            "crm_record_id"
        ].to_list()
    )


def test_duplicate_records_share_ground_truth_lead() -> None:
    config = SimulationConfig(
        target_customers=100,
        target_leads=130,
        duplicate_rate=1.0,
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

    crm, log, mapping = (
        corrupt_crm_leads(
            leads,
            customers,
            config,
        )
    )

    duplicates = mapping.filter(
        pl.col("is_duplicate")
    )

    assert duplicates.height == leads.height

    assert crm.height == (
        leads.height * 2
    )

    assert (
        log.filter(
            pl.col(
                "corruption_type"
            )
            == "duplicate_record"
        ).height
        == leads.height
    )


def test_corruption_is_reproducible() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    first = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    second = corrupt_crm_leads(
        leads,
        customers,
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
