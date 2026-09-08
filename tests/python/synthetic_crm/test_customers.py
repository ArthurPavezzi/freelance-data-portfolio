from synthetic_crm.config import SimulationConfig
from synthetic_crm.customers import generate_customers


def test_customer_generation() -> None:
    config = SimulationConfig(target_customers=500)

    customers = generate_customers(config)

    assert customers.height == 500
    assert customers["customer_id"].n_unique() == 500
    assert customers["canonical_email"].n_unique() == 500
    assert customers["canonical_phone"].n_unique() == 500

    assert customers.null_count().sum_horizontal().item() == 0
