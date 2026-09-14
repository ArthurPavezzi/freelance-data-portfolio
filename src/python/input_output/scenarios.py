from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from input_output.shocks import (
    ShockResult,
    apply_final_demand_shock,
)


@dataclass(frozen=True)
class ShockScenario:
    name: str
    description: str
    delta_final_demand: pd.Series

    def __post_init__(self) -> None:
        if not re.fullmatch(
            r"[a-z0-9_]+",
            self.name,
        ):
            raise ValueError(
                "Scenario name must contain only "
                "lowercase letters, numbers, "
                "and underscores."
            )


@dataclass(frozen=True)
class ScenarioRun:
    scenario: ShockScenario
    result: ShockResult


@dataclass(frozen=True)
class ScenarioOutputPaths:
    summary: Path
    impacts: dict[str, Path]


def run_scenario(
    *,
    scenario: ShockScenario,
    leontief: pd.DataFrame,
    sectors: pd.DataFrame,
) -> ScenarioRun:
    result = apply_final_demand_shock(
        leontief=leontief,
        delta_final_demand=(
            scenario.delta_final_demand
        ),
        sectors=sectors,
    )

    return ScenarioRun(
        scenario=scenario,
        result=result,
    )


def run_scenarios(
    *,
    scenarios: Iterable[ShockScenario],
    leontief: pd.DataFrame,
    sectors: pd.DataFrame,
) -> tuple[ScenarioRun, ...]:
    scenarios = tuple(
        scenarios
    )

    names = [
        scenario.name
        for scenario in scenarios
    ]

    if len(names) != len(
        set(names)
    ):
        raise ValueError(
            "Scenario names must be unique."
        )

    return tuple(
        run_scenario(
            scenario=scenario,
            leontief=leontief,
            sectors=sectors,
        )
        for scenario in scenarios
    )


def compare_scenarios(
    runs: Iterable[ScenarioRun],
) -> pd.DataFrame:
    records = []

    for run in runs:
        records.append(
            {
                "scenario": (
                    run.scenario.name
                ),
                "description": (
                    run.scenario.description
                ),
                "direct_demand_shock": (
                    run.result.direct_demand_shock
                ),
                "total_output_impact": (
                    run.result.total_output_impact
                ),
                "indirect_output_impact": (
                    run.result.indirect_output_impact
                ),
                "output_multiplier": (
                    run.result.output_multiplier
                ),
            }
        )

    return pd.DataFrame(
        records
    )


def write_scenario_outputs(
    *,
    runs: Iterable[ScenarioRun],
    output_dir: str | Path = Path(
        "reports/input-output/scenarios"
    ),
) -> ScenarioOutputPaths:
    runs = tuple(
        runs
    )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path = (
        output_dir
        / "scenario_comparison.csv"
    )

    comparison = compare_scenarios(
        runs
    )

    comparison.to_csv(
        summary_path,
        index=False,
    )

    impact_paths: dict[
        str,
        Path,
    ] = {}

    for run in runs:
        path = (
            output_dir
            / (
                f"{run.scenario.name}"
                "_impacts.csv"
            )
        )

        run.result.sector_impacts.to_csv(
            path,
            index=False,
        )

        impact_paths[
            run.scenario.name
        ] = path

    return ScenarioOutputPaths(
        summary=summary_path,
        impacts=impact_paths,
    )
