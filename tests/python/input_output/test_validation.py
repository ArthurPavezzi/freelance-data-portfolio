import pandas as pd
import pytest
from input_output.validation import (
    compare_matrices,
)


def _matrix(
    values: list[list[float]],
) -> pd.DataFrame:
    return pd.DataFrame(
        values,
        index=[
            "S1",
            "S2",
        ],
        columns=[
            "S1",
            "S2",
        ],
    )


def test_identical_matrices_have_zero_error() -> None:
    calculated = _matrix(
        [
            [1.0, 0.2],
            [0.3, 1.1],
        ]
    )

    official = calculated.copy()

    result = compare_matrices(
        calculated,
        official,
    )

    assert result.max_abs_error == 0.0

    assert result.mean_abs_error == 0.0

    assert result.rmse == 0.0

    assert result.allclose


def test_validation_measures_known_error() -> None:
    official = _matrix(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )

    calculated = _matrix(
        [
            [1.1, 0.0],
            [0.0, 1.0],
        ]
    )

    result = compare_matrices(
        calculated,
        official,
        atol=1e-12,
        rtol=1e-12,
    )

    assert result.max_abs_error == pytest.approx(0.1)

    assert result.mean_abs_error == pytest.approx(0.025)

    assert result.rmse == pytest.approx(0.05)

    assert not result.allclose


def test_validation_respects_tolerance() -> None:
    official = _matrix(
        [
            [1.0, 0.2],
            [0.3, 1.0],
        ]
    )

    calculated = _matrix(
        [
            [1.0 + 1e-8, 0.2],
            [0.3, 1.0],
        ]
    )

    loose = compare_matrices(
        calculated,
        official,
        atol=1e-7,
        rtol=0.0,
    )

    strict = compare_matrices(
        calculated,
        official,
        atol=1e-10,
        rtol=0.0,
    )

    assert loose.allclose
    assert not strict.allclose


def test_validation_rejects_different_shapes() -> None:
    calculated = _matrix(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )

    official = pd.DataFrame(
        [[1.0]],
        index=["S1"],
        columns=["S1"],
    )

    with pytest.raises(
        ValueError,
        match="same shape",
    ):
        compare_matrices(
            calculated,
            official,
        )


def test_validation_rejects_different_row_labels() -> None:
    calculated = _matrix(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )

    official = calculated.copy()

    official.index = [
        "S1",
        "S3",
    ]

    with pytest.raises(
        ValueError,
        match="row labels differ",
    ):
        compare_matrices(
            calculated,
            official,
        )


def test_validation_rejects_different_column_labels() -> None:
    calculated = _matrix(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )

    official = calculated.copy()

    official.columns = [
        "S1",
        "S3",
    ]

    with pytest.raises(
        ValueError,
        match="column labels differ",
    ):
        compare_matrices(
            calculated,
            official,
        )
