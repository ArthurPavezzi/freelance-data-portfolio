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
from synthetic_crm.marketing_export import (
    TRACKABLE_SOURCES,
    generate_marketing_export,
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


def test_marketing_record_ids_are_unique() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    marketing, _, _ = (
        generate_marketing_export(
            leads,
            customers,
            config,
        )
    )

    assert (
        marketing[
            "marketing_record_id"
        ].n_unique()
        == marketing.height
    )


def test_only_trackable_true_sources_are_mapped() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    _, _, mapping = (
        generate_marketing_export(
            leads,
            customers,
            config,
        )
    )

    mapped_lead_ids = set(
        mapping[
            "ground_truth_lead_id"
        ]
        .drop_nulls()
        .to_list()
    )

    eligible_lead_ids = set(
        leads
        .filter(
            pl.col("source").is_in(
                list(
                    TRACKABLE_SOURCES
                )
            )
        )[
            "lead_id"
        ]
        .to_list()
    )

    assert (
        mapped_lead_ids
        .issubset(
            eligible_lead_ids
        )
    )


def test_noise_records_have_no_ground_truth() -> None:
    config = SimulationConfig(
        target_customers=200,
        target_leads=250,
        marketing_test_record_rate=0.10,
        marketing_spam_record_rate=0.10,
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

    _, _, mapping = (
        generate_marketing_export(
            leads,
            customers,
            config,
        )
    )

    noise = mapping.filter(
        pl.col("record_kind")
        .is_in(
            ["test", "spam"]
        )
    )

    assert noise.height > 0

    assert (
        noise[
            "ground_truth_lead_id"
        ].null_count()
        == noise.height
    )


def test_duplicate_submissions_reference_original() -> None:
    config = SimulationConfig(
        target_customers=200,
        target_leads=250,
        marketing_duplicate_rate=1.0,
        marketing_test_record_rate=0.0,
        marketing_spam_record_rate=0.0,
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

    _, _, mapping = (
        generate_marketing_export(
            leads,
            customers,
            config,
        )
    )

    duplicates = mapping.filter(
        pl.col("is_duplicate")
    )

    originals = set(
        mapping
        .filter(
            ~pl.col("is_duplicate")
        )[
            "marketing_record_id"
        ]
        .to_list()
    )

    assert duplicates.height > 0

    assert set(
        duplicates[
            "duplicate_of_marketing_record_id"
        ].to_list()
    ).issubset(originals)


def test_marketing_export_is_reproducible() -> None:
    (
        config,
        customers,
        leads,
    ) = _generate_test_data()

    first = generate_marketing_export(
        leads,
        customers,
        config,
    )

    second = generate_marketing_export(
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
