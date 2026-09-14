from pathlib import Path

import pandas as pd
import pytest
from input_output.scenarios import (
    ShockScenario,
    compare_scenarios,
    run_scenario,
    run_scenarios,
    write_scenario_outputs,
)


def _leontief() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [1.5, 0.2],
            [0.4, 1.3],
        ],
        index=[
            "S1",
            "S2",
        ],
        columns=[
            "S1",
            "S2",
        ],
    )


def _sectors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code": [
                "S1",
                "S2",
            ],
            "name": [
                "Sector 1",
                "Sector 2",
            ],
        }
    )


def _scenario(
    name: str = "baseline",
) -> ShockScenario:
    return ShockScenario(
        name=name,
        description="Test scenario",
        delta_final_demand=pd.Series(
            [100.0, 0.0],
            index=[
                "S1",
                "S2",
            ],
        ),
    )


def test_run_scenario() -> None:
    run = run_scenario(
        scenario=_scenario(),
        leontief=_leontief(),
        sectors=_sectors(),
    )

    assert (
        run.scenario.name
        == "baseline"
    )

    assert (
        run.result.direct_demand_shock
        == pytest.approx(
            100.0
        )
    )

    assert (
        run.result.total_output_impact
        == pytest.approx(
            190.0
        )
    )


def test_run_multiple_scenarios() -> None:
    runs = run_scenarios(
        scenarios=[
            _scenario(
                "scenario_a"
            ),
            _scenario(
                "scenario_b"
            ),
        ],
        leontief=_leontief(),
        sectors=_sectors(),
    )

    assert len(runs) == 2

    assert [
        run.scenario.name
        for run in runs
    ] == [
        "scenario_a",
        "scenario_b",
    ]


def test_duplicate_scenario_names_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        run_scenarios(
            scenarios=[
                _scenario(
                    "duplicate"
                ),
                _scenario(
                    "duplicate"
                ),
            ],
            leontief=_leontief(),
            sectors=_sectors(),
        )


def test_invalid_scenario_name_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Scenario name",
    ):
        ShockScenario(
            name="Investment +10%",
            description=(
                "Invalid name"
            ),
            delta_final_demand=pd.Series(
                [100.0],
                index=["S1"],
            ),
        )


def test_compare_scenarios() -> None:
    runs = run_scenarios(
        scenarios=[
            _scenario(
                "scenario_a"
            ),
            ShockScenario(
                name="scenario_b",
                description=(
                    "Second scenario"
                ),
                delta_final_demand=pd.Series(
                    [
                        0.0,
                        100.0,
                    ],
                    index=[
                        "S1",
                        "S2",
                    ],
                ),
            ),
        ],
        leontief=_leontief(),
        sectors=_sectors(),
    )

    comparison = compare_scenarios(
        runs
    )

    assert comparison.shape == (
        2,
        6,
    )

    assert (
        comparison[
            "scenario"
        ].tolist()
        == [
            "scenario_a",
            "scenario_b",
        ]
    )

    assert (
        "output_multiplier"
        in comparison.columns
    )


def test_write_scenario_outputs(
    tmp_path: Path,
) -> None:
    runs = run_scenarios(
        scenarios=[
            _scenario(
                "scenario_a"
            ),
            _scenario(
                "scenario_b"
            ),
        ],
        leontief=_leontief(),
        sectors=_sectors(),
    )

    paths = write_scenario_outputs(
        runs=runs,
        output_dir=tmp_path,
    )

    assert (
        paths.summary.exists()
    )

    assert (
        paths.impacts[
            "scenario_a"
        ].exists()
    )

    assert (
        paths.impacts[
            "scenario_b"
        ].exists()
    )


def test_written_summary_roundtrip(
    tmp_path: Path,
) -> None:
    runs = run_scenarios(
        scenarios=[
            _scenario(),
        ],
        leontief=_leontief(),
        sectors=_sectors(),
    )

    paths = write_scenario_outputs(
        runs=runs,
        output_dir=tmp_path,
    )

    summary = pd.read_csv(
        paths.summary
    )

    assert (
        summary.loc[
            0,
            "scenario",
        ]
        == "baseline"
    )

    assert (
        summary.loc[
            0,
            "direct_demand_shock",
        ]
        == pytest.approx(
            100.0
        )
    )


def test_written_impacts_roundtrip(
    tmp_path: Path,
) -> None:
    runs = run_scenarios(
        scenarios=[
            _scenario(),
        ],
        leontief=_leontief(),
        sectors=_sectors(),
    )

    paths = write_scenario_outputs(
        runs=runs,
        output_dir=tmp_path,
    )

    impacts = pd.read_csv(
        paths.impacts[
            "baseline"
        ]
    )

    assert len(impacts) == 2

    assert (
        impacts[
            "sector_code"
        ].tolist()
        == [
            "S1",
            "S2",
        ]
    )
