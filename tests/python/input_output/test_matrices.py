from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from input_output.matrices import (
    build_leontief_inverse,
    build_technical_matrix,
)
from input_output.parse import (
    parse_ibge_workbook,
)

WORKBOOK = Path(
    "data/raw/ibge_mip/2015/"
    "Matriz_de_Insumo_Produto_2015_Nivel_67.xls"
)


def test_build_technical_matrix() -> None:
    D = pd.DataFrame(
        [
            [0.8, 0.2],
            [0.1, 0.9],
        ],
        index=[
            "S1",
            "S2",
        ],
        columns=[
            "P1",
            "P2",
        ],
    )

    Bn = pd.DataFrame(
        [
            [0.2, 0.1],
            [0.3, 0.4],
        ],
        index=[
            "P1",
            "P2",
        ],
        columns=[
            "S1",
            "S2",
        ],
    )

    result = build_technical_matrix(
        D,
        Bn,
    )

    expected = pd.DataFrame(
        [
            [0.22, 0.16],
            [0.29, 0.37],
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

    np.testing.assert_allclose(
        result.to_numpy(),
        expected.to_numpy(),
    )

    assert (
        result.index.tolist()
        == ["S1", "S2"]
    )

    assert (
        result.columns.tolist()
        == ["S1", "S2"]
    )


def test_build_technical_matrix_requires_aligned_products() -> None:
    D = pd.DataFrame(
        [[1.0, 0.0]],
        index=["S1"],
        columns=["P1", "P2"],
    )

    Bn = pd.DataFrame(
        [
            [0.1],
            [0.2],
        ],
        index=[
            "P2",
            "P1",
        ],
        columns=["S1"],
    )

    with pytest.raises(
        ValueError,
        match="Product codes are not aligned",
    ):
        build_technical_matrix(
            D,
            Bn,
        )


def test_build_leontief_inverse() -> None:
    A = pd.DataFrame(
        [
            [0.2, 0.1],
            [0.3, 0.2],
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

    result = build_leontief_inverse(
        A
    )

    expected = np.linalg.inv(
        np.eye(2)
        - A.to_numpy()
    )

    np.testing.assert_allclose(
        result.to_numpy(),
        expected,
    )

    assert (
        result.index.tolist()
        == A.index.tolist()
    )

    assert (
        result.columns.tolist()
        == A.columns.tolist()
    )


def test_build_leontief_inverse_requires_square_matrix() -> None:
    A = pd.DataFrame(
        [
            [0.1, 0.2],
        ],
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
        build_leontief_inverse(
            A
        )


def test_build_leontief_inverse_requires_aligned_sector_labels() -> None:
    A = pd.DataFrame(
        [
            [0.1, 0.2],
            [0.3, 0.1],
        ],
        index=[
            "S1",
            "S2",
        ],
        columns=[
            "S2",
            "S1",
        ],
    )

    with pytest.raises(
        ValueError,
        match=(
            "Sector rows and columns "
            "must be aligned"
        ),
    ):
        build_leontief_inverse(
            A
        )


@pytest.mark.skipif(
    not WORKBOOK.exists(),
    reason=(
        "IBGE workbook has not been "
        "downloaded."
    ),
)
def test_reconstructed_ibge_matrices_match_official_tables() -> None:
    tables = parse_ibge_workbook(
        WORKBOOK
    )

    A = build_technical_matrix(
        tables.D,
        tables.Bn,
    )

    L = build_leontief_inverse(
        A
    )

    np.testing.assert_allclose(
        A.to_numpy(),
        tables.A_official.to_numpy(),
        rtol=1e-12,
        atol=1e-12,
    )

    np.testing.assert_allclose(
        L.to_numpy(),
        tables.L_official.to_numpy(),
        rtol=1e-12,
        atol=1e-12,
    )
