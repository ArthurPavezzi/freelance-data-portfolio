from crm_reconciliation.run import (
    PIPELINE_STAGES,
)


def test_pipeline_stage_order() -> None:
    assert [name for name, _ in PIPELINE_STAGES] == [
        "Exact matching",
        "Fuzzy candidate recovery",
        "Match resolution",
        "Entity clustering",
        "Unified lead ledger",
        "Observable triage",
        "Within-system deduplication",
        "Acquisition reconstruction",
        "Operational reporting",
    ]


def test_validation_is_not_an_operational_stage() -> None:
    stage_modules = [stage.__module__ for _, stage in PIPELINE_STAGES]

    assert "crm_reconciliation.run_validation" not in stage_modules
