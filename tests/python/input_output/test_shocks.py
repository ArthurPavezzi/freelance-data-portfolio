import numpy as np
import pandas as pd
import pytest

from input_output.shocks import (
    apply_final_demand_shock,
    build_sector_shock,
    build_group_shock,
    build_percentage_shock,
    rescale_shock_to_total,
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


def test_build_sector_shock() -> None:
    shock = build_sector_shock(
        sector_codes=pd.Index(
            ["S1", "S2", "S3"]
        ),
        sector_code="S2",
        amount=100.0,
    )

    assert shock.tolist() == [
        0.0,
        100.0,
        0.0,
    ]


def test_build_group_shock() -> None:
    shock = build_group_shock(
        sector_codes=pd.Index(
            ["S1", "S2", "S3"]
        ),
        shocks={
            "S1": 100.0,
            "S3": 50.0,
        },
    )

    assert shock.tolist() == [
        100.0,
        0.0,
        50.0,
    ]


def test_build_percentage_shock() -> None:
    final_demand = pd.Series(
        [100.0, 200.0, 300.0],
        index=["S1", "S2", "S3"],
    )

    shock = build_percentage_shock(
        final_demand=final_demand,
        sector_codes=[
            "S1",
            "S3",
        ],
        rate=0.40,
    )

    assert shock.tolist() == [
        40.0,
        0.0,
        120.0,
    ]


def test_sector_shock_rejects_unknown_sector() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown sector code",
    ):
        build_sector_shock(
            sector_codes=pd.Index(
                ["S1"]
            ),
            sector_code="S2",
            amount=100.0,
        )


def test_group_shock_rejects_unknown_sector() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown sector codes",
    ):
        build_group_shock(
            sector_codes=pd.Index(
                ["S1"]
            ),
            shocks={
                "S2": 100.0,
            },
        )


def test_percentage_shock_rejects_unknown_sector() -> None:
    final_demand = pd.Series(
        [100.0],
        index=["S1"],
    )

    with pytest.raises(
        ValueError,
        match="Unknown sector codes",
    ):
        build_percentage_shock(
            final_demand=final_demand,
            sector_codes=[
                "S2",
            ],
            rate=0.40,
        )


def test_rescale_shock_to_total() -> None:
    shock = pd.Series(
        [
            20.0,
            30.0,
            50.0,
        ],
        index=[
            "S1",
            "S2",
            "S3",
        ],
    )

    result = rescale_shock_to_total(
        delta_final_demand=shock,
        target_total=1_000.0,
    )

    assert (
        result.sum()
        == pytest.approx(
            1_000.0
        )
    )

    assert result.tolist() == pytest.approx(
        [
            200.0,
            300.0,
            500.0,
        ]
    )


def test_rescale_preserves_composition() -> None:
    shock = pd.Series(
        [
            25.0,
            75.0,
        ],
        index=[
            "S1",
            "S2",
        ],
    )

    result = rescale_shock_to_total(
        delta_final_demand=shock,
        target_total=500.0,
    )

    assert (
        result.loc["S1"]
        / result.loc["S2"]
        == pytest.approx(
            1 / 3
        )
    )


def test_rescale_rejects_zero_net_shock() -> None:
    shock = pd.Series(
        [
            100.0,
            -100.0,
        ],
        index=[
            "S1",
            "S2",
        ],
    )

    with pytest.raises(
        ValueError,
        match="zero net total",
    ):
        rescale_shock_to_total(
            delta_final_demand=shock,
            target_total=1_000.0,
        )


def test_rescale_rejects_nonfinite_target() -> None:
    shock = pd.Series(
        [
            100.0,
        ],
        index=[
            "S1",
        ],
    )

    with pytest.raises(
        ValueError,
        match="must be finite",
    ):
        rescale_shock_to_total(
            delta_final_demand=shock,
            target_total=np.inf,
        )
