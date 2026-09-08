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
        missing_crm_lead_rate=0.0,
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
        

def test_missing_crm_leads_are_not_observed() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
        missing_crm_lead_rate=0.20,
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

    _, log, mapping = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    omitted = set(
        log
        .filter(
            pl.col("corruption_type")
            == "missing_crm_lead"
        )["ground_truth_lead_id"]
        .to_list()
    )

    observed = set(
        mapping[
            "ground_truth_lead_id"
        ].to_list()
    )

    assert omitted
    assert omitted.isdisjoint(observed)


def test_source_aliases_are_logged() -> None:
    config = SimulationConfig(
        target_customers=200,
        target_leads=250,
        missing_crm_lead_rate=0.0,
        missing_source_rate=0.0,
        source_alias_rate=1.0,
    )

    customers = generate_customers(config)
    base_leads = generate_leads(customers, config)

    _, leads, _, _ = generate_funnel(
        base_leads,
        customers,
        config,
    )

    _, log, _ = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    aliases = log.filter(
        pl.col("corruption_type")
        == "source_alias"
    )

    assert aliases.height == leads.height


def test_missing_contact_fields_are_logged() -> None:
    config = SimulationConfig(
        target_customers=200,
        target_leads=250,
        missing_phone_rate=1.0,
        malformed_phone_rate=0.0,
        phone_format_rate=0.0,
        missing_email_rate=1.0,
        malformed_email_rate=0.0,
        missing_crm_lead_rate=0.0,
    )

    customers = generate_customers(config)
    base_leads = generate_leads(customers, config)

    _, leads, _, _ = generate_funnel(
        base_leads,
        customers,
        config,
    )

    crm, _, _ = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    assert crm["phone"].null_count() == crm.height
    assert crm["email"].null_count() == crm.height
