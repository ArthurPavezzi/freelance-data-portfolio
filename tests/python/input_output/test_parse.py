from pathlib import Path

import pandas as pd
import pytest

from input_output.parse import (
    _extract_code,
    _parse_final_demand_frame,
    _parse_matrix_frame,
    parse_ibge_workbook
)


WORKBOOK = Path(
    "data/raw/ibge_mip/2015/"
    "Matriz_de_Insumo_Produto_2015_Nivel_67.xls"
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


def test_parse_final_demand_frame() -> None:
    raw = pd.DataFrame(
        {
            "Código": [
                "01911",
                "01912",
            ],
            "Descrição": [
                "Product 1",
                "Product 2",
            ],
            "Exportação\nde bens e\nserviços": [
                10.0,
                20.0,
            ],
            "Consumo\ndo governo": [
                1.0,
                2.0,
            ],
            "Consumo\ndas\n ISFLSF": [
                3.0,
                4.0,
            ],
            "Consumo \ndas famílias": [
                30.0,
                40.0,
            ],
            "Formação bruta\nde capital fixo": [
                5.0,
                6.0,
            ],
            "Variação\nde estoque": [
                -1.0,
                2.0,
            ],
            "Demanda\nfinal": [
                48.0,
                74.0,
            ],
        }
    )

    result = (
        _parse_final_demand_frame(
            raw,
            expected_rows=2,
        )
    )

    assert result.shape == (
        2,
        7,
    )

    assert (
        result.index.tolist()
        == [
            "01911",
            "01912",
        ]
    )

    assert (
        result.columns.tolist()
        == [
            "exports",
            "government_consumption",
            "npish_consumption",
            "household_consumption",
            "gross_fixed_capital_formation",
            "inventory_change",
            "total_final_demand",
        ]
    )


def test_final_demand_components_sum_to_total() -> None:
    raw = pd.DataFrame(
        {
            "Código": [
                "01911",
            ],
            "Descrição": [
                "Product 1",
            ],
            "Exportação de bens e serviços": [
                10.0,
            ],
            "Consumo do governo": [
                20.0,
            ],
            "Consumo das ISFLSF": [
                5.0,
            ],
            "Consumo das famílias": [
                50.0,
            ],
            "Formação bruta de capital fixo": [
                15.0,
            ],
            "Variação de estoque": [
                -2.0,
            ],
            "Demanda final": [
                98.0,
            ],
        }
    )

    result = (
        _parse_final_demand_frame(
            raw,
            expected_rows=1,
        )
    )

    components = [
        "exports",
        "government_consumption",
        "npish_consumption",
        "household_consumption",
        "gross_fixed_capital_formation",
        "inventory_change",
    ]

    assert (
        result.loc[
            "01911",
            components,
        ].sum()
        == pytest.approx(
            result.loc[
                "01911",
                "total_final_demand",
            ]
        )
    )


@pytest.mark.skipif(
    not WORKBOOK.exists(),
    reason=(
        "IBGE workbook has not been "
        "downloaded."
    ),
)
def test_real_workbook_final_demand() -> None:
    tables = parse_ibge_workbook(
        WORKBOOK
    )

    assert (
        tables.final_demand_by_product.shape
        == (127, 7)
    )

    assert (
        tables.final_demand_by_sector.shape
        == (67, 7)
    )

    assert (
        len(
            tables.final_demand
        )
        == 67
    )

    assert not (
        tables.final_demand
        .isna()
        .any()
    )
