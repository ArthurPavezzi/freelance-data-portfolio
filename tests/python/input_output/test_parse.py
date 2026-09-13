import pandas as pd
import pytest

from input_output.parse import (
    _extract_code,
    _parse_matrix_frame,
)


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        ("0191", 4, "0191"),
        (
            "0191\nAgricultura",
            4,
            "0191",
        ),
        (191, 4, "0191"),
        (191.0, 4, "0191"),
        ("01911", 5, "01911"),
        ("Total", 4, None),
        (None, 4, None),
    ],
)
def test_extract_code(
    value,
    digits,
    expected,
) -> None:
    assert (
        _extract_code(
            value,
            digits=digits,
        )
        == expected
    )


def test_parse_matrix_frame() -> None:
    raw = pd.DataFrame(
        {
            "Código": [
                "01911",
                "01912",
                "01913",
                "Total",
            ],
            "Descrição": [
                "Product A",
                "Product B",
                "Product C",
                None,
            ],
            "0191\nSector A": [
                0.10,
                0.20,
                0.30,
                0.60,
            ],
            "0192\nSector B": [
                0.40,
                0.50,
                0.60,
                1.50,
            ],
            "Total": [
                0.50,
                0.70,
                0.90,
                2.10,
            ],
        }
    )

    parsed = _parse_matrix_frame(
        raw,
        row_digits=5,
        column_digits=4,
        expected_shape=(
            3,
            2,
        ),
    )

    assert (
        parsed.values.shape
        == (3, 2)
    )

    assert (
        parsed.values.index.tolist()
        == [
            "01911",
            "01912",
            "01913",
        ]
    )

    assert (
        parsed.values.columns.tolist()
        == [
            "0191",
            "0192",
        ]
    )

    assert (
        parsed.column_labels[
            "name"
        ].tolist()
        == [
            "Sector A",
            "Sector B",
        ]
    )


def test_parser_rejects_wrong_shape() -> None:
    raw = pd.DataFrame(
        {
            "Código": [
                "01911",
            ],
            "Descrição": [
                "Product A",
            ],
            "0191\nSector A": [
                0.1,
            ],
        }
    )

    with pytest.raises(
        ValueError,
        match="Unexpected matrix shape",
    ):
        _parse_matrix_frame(
            raw,
            row_digits=5,
            column_digits=4,
            expected_shape=(
                127,
                67,
            ),
        )
