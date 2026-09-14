import pandas as pd
import pytest
from input_output.linkages import (
    classify_sector,
    rasmussen_hirschman,
)


@pytest.mark.parametrize(
    (
        "forward",
        "backward",
        "expected",
    ),
    [
        (0.8, 0.9, "I"),
        (1.2, 0.9, "II"),
        (1.2, 1.1, "III"),
        (0.8, 1.1, "IV"),
        (1.0, 1.0, "III"),
    ],
)
def test_classify_sector(
    forward,
    backward,
    expected,
) -> None:
    assert (
        classify_sector(
            forward_linkage=forward,
            backward_linkage=backward,
        )
        == expected
    )


def test_rasmussen_hirschman() -> None:
    L = pd.DataFrame(
        [
            [2.0, 1.0],
            [0.5, 1.5],
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

    result = rasmussen_hirschman(
        L,
        sectors,
    )

    overall_mean = (
        L.to_numpy().mean()
    )

    assert (
        result.loc[
            0,
            "forward_linkage",
        ]
        == pytest.approx(
            L.iloc[
                0
            ].mean()
            / overall_mean
        )
    )

    assert (
        result.loc[
            0,
            "backward_linkage",
        ]
        == pytest.approx(
            L.iloc[
                :,
                0,
            ].mean()
            / overall_mean
        )
    )


def test_linkage_indices_average_to_one() -> None:
    L = pd.DataFrame(
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

    result = rasmussen_hirschman(
        L,
        sectors,
    )

    assert (
        result[
            "forward_linkage"
        ].mean()
        == pytest.approx(
            1.0
        )
    )

    assert (
        result[
            "backward_linkage"
        ].mean()
        == pytest.approx(
            1.0
        )
    )


def test_rasmussen_hirschman_rejects_non_square_matrix() -> None:
    L = pd.DataFrame(
        [[1.0, 0.2]],
        index=["S1"],
        columns=[
            "S1",
            "S2",
        ],
    )

    sectors = pd.DataFrame(
        {
            "code": ["S1"],
            "name": ["Sector 1"],
        }
    )

    with pytest.raises(
        ValueError,
        match="must be square",
    ):
        rasmussen_hirschman(
            L,
            sectors,
        )


def test_rasmussen_hirschman_rejects_misaligned_matrix() -> None:
    L = pd.DataFrame(
        [
            [1.0, 0.2],
            [0.3, 1.0],
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

    with pytest.raises(
        ValueError,
        match="rows and columns",
    ):
        rasmussen_hirschman(
            L,
            sectors,
        )


def test_rasmussen_hirschman_rejects_misaligned_metadata() -> None:
    L = pd.DataFrame(
        [
            [1.0, 0.2],
            [0.3, 1.0],
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

    sectors = pd.DataFrame(
        {
            "code": [
                "S2",
                "S1",
            ],
            "name": [
                "Sector 2",
                "Sector 1",
            ],
        }
    )

    with pytest.raises(
        ValueError,
        match="metadata is not aligned",
    ):
        rasmussen_hirschman(
            L,
            sectors,
        )
