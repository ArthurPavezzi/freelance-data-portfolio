from synthetic_crm.config import SimulationConfig
from synthetic_crm.customers import generate_customers
from synthetic_crm.funnel import generate_funnel
from synthetic_crm.marketing import generate_leads


def test_funnel_generation() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)

    base_leads = generate_leads(
        customers,
        config,
    )

    (
        salespeople,
        leads,
        estimates,
        jobs,
    ) = generate_funnel(
        base_leads,
        customers,
        config,
    )

    assert salespeople.height == 4

    assert leads.height == base_leads.height

    assert (
        leads["lead_id"].n_unique()
        == leads.height
    )

    assert (
        estimates["estimate_id"].n_unique()
        == estimates.height
    )

    assert (
        jobs["job_id"].n_unique()
        == jobs.height
    )


def test_funnel_relational_integrity() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)
    base_leads = generate_leads(customers, config)

    (
        _,
        leads,
        estimates,
        jobs,
    ) = generate_funnel(
        base_leads,
        customers,
        config,
    )

    lead_ids = set(
        leads["lead_id"].to_list()
    )

    estimate_ids = set(
        estimates["estimate_id"].to_list()
    )

    assert set(
        estimates["lead_id"].to_list()
    ).issubset(lead_ids)

    assert set(
        jobs["lead_id"].to_list()
    ).issubset(lead_ids)

    assert set(
        jobs["estimate_id"].to_list()
    ).issubset(estimate_ids)


def test_only_won_estimates_create_jobs() -> None:
    config = SimulationConfig(
        target_customers=500,
        target_leads=700,
    )

    customers = generate_customers(config)
    base_leads = generate_leads(customers, config)

    (
        _,
        _,
        estimates,
        jobs,
    ) = generate_funnel(
        base_leads,
        customers,
        config,
    )

    won_estimates = set(
        estimates
        .filter(
            estimates["status"] == "Won"
        )["estimate_id"]
        .to_list()
    )

    job_estimates = set(
        jobs["estimate_id"].to_list()
    )

    assert job_estimates == won_estimates
