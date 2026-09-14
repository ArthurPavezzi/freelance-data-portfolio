from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ShockResult:
    sector_impacts: pd.DataFrame
    direct_demand_shock: float
    total_output_impact: float
    indirect_output_impact: float
    output_multiplier: float


def apply_final_demand_shock(
    *,
    leontief: pd.DataFrame,
    delta_final_demand: pd.Series,
    sectors: pd.DataFrame | None = None,
) -> ShockResult:
    """
    Apply an exogenous final-demand shock using:

        Δx = L @ Δy

    where:
        L  = Leontief inverse
        Δy = final-demand shock
        Δx = total output impact
    """
    if leontief.shape[0] != leontief.shape[1]:
        raise ValueError(
            "Leontief matrix must be square."
        )

    if list(leontief.index) != list(
        leontief.columns
    ):
        raise ValueError(
            "Sector rows and columns must be aligned."
        )

    if delta_final_demand.index.has_duplicates:
        raise ValueError(
            "Final-demand shock contains duplicate sector codes."
        )

    matrix_codes = list(
        leontief.index
    )

    shock_codes = list(
        delta_final_demand.index
    )

    if set(matrix_codes) != set(
        shock_codes
    ):
        raise ValueError(
            "Final-demand shock sector codes "
            "do not match the Leontief matrix."
        )

    delta_y = (
        delta_final_demand
        .reindex(matrix_codes)
        .astype(float)
    )

    if delta_y.isna().any():
        raise ValueError(
            "Final-demand shock contains missing values."
        )

    if not np.isfinite(
        delta_y.to_numpy()
    ).all():
        raise ValueError(
            "Final-demand shock contains non-finite values."
        )

    delta_x = pd.Series(
        leontief.to_numpy()
        @ delta_y.to_numpy(),
        index=matrix_codes,
        name="total_output_impact",
    )

    indirect = (
        delta_x
        - delta_y
    )

    impacts = pd.DataFrame(
        {
            "sector_code": matrix_codes,
            "direct_demand_shock": (
                delta_y.to_numpy()
            ),
            "total_output_impact": (
                delta_x.to_numpy()
            ),
            "indirect_output_impact": (
                indirect.to_numpy()
            ),
        }
    )

    if sectors is not None:
        required = {
            "code",
            "name",
        }

        if not required.issubset(
            sectors.columns
        ):
            raise ValueError(
                "sectors must contain "
                "'code' and 'name' columns."
            )

        metadata = (
            sectors[
                [
                    "code",
                    "name",
                ]
            ]
            .rename(
                columns={
                    "code": "sector_code",
                    "name": "sector_name",
                }
            )
        )

        impacts = impacts.merge(
            metadata,
            on="sector_code",
            how="left",
            validate="one_to_one",
        )

        if impacts[
            "sector_name"
        ].isna().any():
            raise ValueError(
                "Sector metadata is incomplete."
            )

        impacts = impacts[
            [
                "sector_code",
                "sector_name",
                "direct_demand_shock",
                "total_output_impact",
                "indirect_output_impact",
            ]
        ]

    total_direct = float(
        delta_y.sum()
    )

    total_output = float(
        delta_x.sum()
    )

    total_indirect = (
        total_output
        - total_direct
    )

    multiplier = (
        total_output
        / total_direct
        if not np.isclose(
            total_direct,
            0.0,
        )
        else np.nan
    )

    if not np.isclose(
        total_output,
        0.0,
    ):
        impacts[
            "share_of_total_impact"
        ] = (
            impacts[
                "total_output_impact"
            ]
            / total_output
        )

    else:
        impacts[
            "share_of_total_impact"
        ] = np.nan

    return ShockResult(
        sector_impacts=impacts,
        direct_demand_shock=total_direct,
        total_output_impact=total_output,
        indirect_output_impact=total_indirect,
        output_multiplier=float(
            multiplier
        ),
    )
