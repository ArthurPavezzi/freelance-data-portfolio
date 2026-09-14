from __future__ import annotations

import pandas as pd


def rasmussen_hirschman(
    leontief: pd.DataFrame,
    sectors: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute Rasmussen-Hirschman forward and backward linkages.

    backward_linkage:
        Column mean of the Leontief inverse relative to the
        overall matrix mean.

    forward_linkage:
        Row mean of the Leontief inverse relative to the
        overall matrix mean.
    """
    if leontief.shape[0] != leontief.shape[1]:
        raise ValueError("Leontief matrix must be square.")

    if list(leontief.index) != list(leontief.columns):
        raise ValueError("Sector rows and columns must be aligned.")

    required_columns = {
        "code",
        "name",
    }

    if not required_columns.issubset(sectors.columns):
        raise ValueError("sectors must contain 'code' and 'name' columns.")

    sector_codes = sectors["code"].astype(str).tolist()

    if sector_codes != list(leontief.index):
        raise ValueError("Sector metadata is not aligned with the Leontief matrix.")

    overall_mean = leontief.to_numpy().mean()

    backward = leontief.mean(axis=0) / overall_mean

    forward = leontief.mean(axis=1) / overall_mean

    result = sectors[
        [
            "code",
            "name",
        ]
    ].copy()

    result = result.rename(
        columns={
            "code": "sector_code",
            "name": "sector_name",
        }
    )

    result["forward_linkage"] = forward.to_numpy()

    result["backward_linkage"] = backward.to_numpy()

    result["sector_type"] = [
        classify_sector(
            forward_linkage=f,
            backward_linkage=b,
        )
        for f, b in zip(
            result["forward_linkage"],
            result["backward_linkage"],
        )
    ]

    result["is_key_sector"] = result["sector_type"] == "III"

    return result


def classify_sector(
    *,
    forward_linkage: float,
    backward_linkage: float,
) -> str:
    """
    Classify sectors using Rasmussen-Hirschman linkages.

    Type I:
        forward < 1 and backward < 1

    Type II:
        forward >= 1 and backward < 1

    Type III:
        forward >= 1 and backward >= 1

    Type IV:
        forward < 1 and backward >= 1
    """
    if forward_linkage < 1 and backward_linkage < 1:
        return "I"

    if forward_linkage >= 1 and backward_linkage < 1:
        return "II"

    if forward_linkage >= 1 and backward_linkage >= 1:
        return "III"

    return "IV"
