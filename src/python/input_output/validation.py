from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MatrixValidation:
    max_abs_error: float
    mean_abs_error: float
    rmse: float
    allclose: bool


def compare_matrices(
    calculated: pd.DataFrame,
    official: pd.DataFrame,
    *,
    atol: float = 1e-6,
    rtol: float = 1e-6,
) -> MatrixValidation:
    if calculated.shape != official.shape:
        raise ValueError(
            "Matrices must have the same shape."
        )

    if list(calculated.index) != list(official.index):
        raise ValueError(
            "Matrix row labels differ."
        )

    if list(calculated.columns) != list(official.columns):
        raise ValueError(
            "Matrix column labels differ."
        )

    diff = (
        calculated.to_numpy()
        - official.to_numpy()
    )

    abs_diff = np.abs(
        diff
    )

    return MatrixValidation(
        max_abs_error=float(
            abs_diff.max()
        ),
        mean_abs_error=float(
            abs_diff.mean()
        ),
        rmse=float(
            np.sqrt(
                np.mean(
                    diff**2
                )
            )
        ),
        allclose=bool(
            np.allclose(
                calculated.to_numpy(),
                official.to_numpy(),
                atol=atol,
                rtol=rtol,
            )
        ),
    )
