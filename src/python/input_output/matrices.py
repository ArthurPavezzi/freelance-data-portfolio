from __future__ import annotations

import numpy as np
import pandas as pd


def build_technical_matrix(
    D: pd.DataFrame,
    Bn: pd.DataFrame,
) -> pd.DataFrame:
    if list(D.columns) != list(Bn.index):
        raise ValueError(
            "Product codes are not aligned between D and Bn."
        )

    A = D @ Bn

    A.index.name = "sector_code"
    A.columns.name = "sector_code"

    return A


def build_leontief_inverse(
    A: pd.DataFrame,
) -> pd.DataFrame:
    if A.shape[0] != A.shape[1]:
        raise ValueError(
            "Technical coefficient matrix must be square."
        )

    if list(A.index) != list(A.columns):
        raise ValueError(
            "Sector rows and columns must be aligned."
        )

    identity = np.eye(
        A.shape[0]
    )

    values = np.linalg.inv(
        identity - A.to_numpy()
    )

    return pd.DataFrame(
        values,
        index=A.index.copy(),
        columns=A.columns.copy(),
    )
