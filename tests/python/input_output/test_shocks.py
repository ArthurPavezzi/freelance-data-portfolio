import numpy as np
import pandas as pd
import pytest

from input_output.shocks import (
    apply_final_demand_shock,
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


def test_final_demand_shock_uses_leontief_identity() -> None:
    L = _leontief()

    delta_y = pd.Series(
        [
            100.0,
            0.0,
        ],
        index=[
            "S1",
            "S2",
        ],
    )

    result = apply_final_demand_shock(
        leontief=L,
        delta_final_demand=delta_y,
    )

    expected = (
        L.to_numpy()
        @ delta_y.to_numpy()
    )

    np.testing.assert_allclose(
        result.sector_impacts[
            "total_output_impact"
        ],
        expected,
    )


def test_indirect_impact_is_total_minus_direct() -> None:
    result = apply_final_demand_shock(
        leontief=_leontief(),
        delta_final_demand=pd.Series(
            [100.0, 50.0],
            index=["S1", "S2"],
        ),
    )

    impacts = result.sector_impacts

    np.testing.assert_allclose(
        impacts[
            "indirect_output_impact"
        ],
        (
            impacts[
                "total_output_impact"
            ]
            - impacts[
                "direct_demand_shock"
            ]
        ),
    )


def test_scenario_totals_are_consistent() -> None:
    result = apply_final_demand_shock(
        leontief=_leontief(),
        delta_final_demand=pd.Series(
            [100.0, 50.0],
            index=["S1", "S2"],
        ),
    )

    assert (
        result.indirect_output_impact
        == pytest.approx(
            result.total_output_impact
            - result.direct_demand_shock
        )
    )

    assert (
        result.output_multiplier
        == pytest.approx(
            result.total_output_impact
            / result.direct_demand_shock
        )
    )


def test_shock_is_reordered_to_matrix_sectors() -> None:
    result = apply_final_demand_shock(
        leontief=_leontief(),
        delta_final_demand=pd.Series(
            [50.0, 100.0],
            index=[
                "S2",
                "S1",
            ],
        ),
    )

    assert (
        result.sector_impacts[
            "sector_code"
        ].tolist()
        == [
            "S1",
            "S2",
        ]
    )

    assert (
        result.sector_impacts[
            "direct_demand_shock"
        ].tolist()
        == [
            100.0,
            50.0,
        ]
    )


def test_sector_metadata_is_added() -> None:
    sectors = pd.DataFrame(
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

    result = apply_final_demand_shock(
        leontief=_leontief(),
        delta_final_demand=pd.Series(
            [100.0, 0.0],
            index=["S1", "S2"],
        ),
        sectors=sectors,
    )

    assert (
        result.sector_impacts[
            "sector_name"
        ].tolist()
        == [
            "Sector 1",
            "Sector 2",
        ]
    )


def test_zero_net_shock_has_undefined_multiplier() -> None:
    result = apply_final_demand_shock(
        leontief=_leontief(),
        delta_final_demand=pd.Series(
            [100.0, -100.0],
            index=["S1", "S2"],
        ),
    )

    assert np.isnan(
        result.output_multiplier
    )


def test_rejects_missing_sector_codes() -> None:
    with pytest.raises(
        ValueError,
        match="do not match",
    ):
        apply_final_demand_shock(
            leontief=_leontief(),
            delta_final_demand=pd.Series(
                [100.0],
                index=["S1"],
            ),
        )


def test_rejects_non_square_leontief_matrix() -> None:
    L = pd.DataFrame(
        [[1.0, 0.2]],
        index=["S1"],
        columns=[
            "S1",
            "S2",
        ],
    )

    with pytest.raises(
        ValueError,
        match="must be square",
    ):
        apply_final_demand_shock(
            leontief=L,
            delta_final_demand=pd.Series(
                [100.0],
                index=["S1"],
            ),
        )
