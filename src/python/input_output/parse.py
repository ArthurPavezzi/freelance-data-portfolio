from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IOTables:
    """
    Parsed IBGE input-output tables.

    Bn:
        product x sector
        127 x 67

    D:
        sector x product
        67 x 127

    A_official:
        sector x sector
        67 x 67

    L_official:
        sector x sector
        67 x 67

    final_demand_by_product:
        product x final-demand component
        127 x 7

    final_demand_by_sector:
        sector x final-demand component
        67 x 7
    """

    Bn: pd.DataFrame
    D: pd.DataFrame
    A_official: pd.DataFrame
    L_official: pd.DataFrame

    final_demand_by_product: pd.DataFrame
    final_demand_by_sector: pd.DataFrame

    sectors: pd.DataFrame
    products: pd.DataFrame

    @property
    def final_demand(
        self,
    ) -> pd.Series:
        return (
            self.final_demand_by_sector[
                "total_final_demand"
            ]
            .rename(
                "final_demand"
            )
        )


@dataclass(frozen=True)
class _ParsedMatrix:
    values: pd.DataFrame
    row_labels: pd.DataFrame
    column_labels: pd.DataFrame


FINAL_DEMAND_COLUMNS = {
    "exportação de bens e serviços":
        "exports",

    "consumo do governo":
        "government_consumption",

    "consumo das isflsf":
        "npish_consumption",

    "consumo das famílias":
        "household_consumption",

    "formação bruta de capital fixo":
        "gross_fixed_capital_formation",

    "variação de estoque":
        "inventory_change",

    "demanda final":
        "total_final_demand",
}


def _extract_code(
    value: object,
    *,
    digits: int,
) -> str | None:
    """
    Extract an IBGE code while preserving leading zeros.

    Works with:
        "0191"
        "0191\\nAgricultura..."
        191
        191.0
    """
    if pd.isna(value):
        return None

    if isinstance(
        value,
        (int, float),
    ):
        if (
            isinstance(value, float)
            and not value.is_integer()
        ):
            return None

        text = str(
            int(value)
        ).zfill(
            digits
        )

    else:
        text = str(
            value
        ).strip()

    match = re.match(
        r"^(\d+)",
        text,
    )

    if match is None:
        return None

    code = match.group(1)

    if len(code) > digits:
        return None

    return code.zfill(
        digits
    )


def _normalize_header(
    value: object,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value)
        .replace(
            "\n",
            " ",
        )
        .strip()
        .casefold(),
    )


def _extract_header_name(
    value: object,
    *,
    digits: int,
) -> str:
    text = str(
        value
    ).strip()

    text = re.sub(
        rf"^\s*\d{{1,{digits}}}\s*",
        "",
        text,
    )

    text = text.replace(
        "\n",
        " ",
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _parse_matrix_frame(
    raw: pd.DataFrame,
    *,
    row_digits: int,
    column_digits: int,
    expected_shape: tuple[int, int],
) -> _ParsedMatrix:
    """
    Parse one IBGE worksheet after pandas has read its header.

    The parser identifies economic rows/columns from IBGE codes,
    rather than relying on absolute Excel row/column positions.
    """
    if raw.shape[1] < 3:
        raise ValueError(
            "Worksheet contains too few columns."
        )

    row_code_raw = raw.iloc[
        :,
        0,
    ]

    row_name_raw = raw.iloc[
        :,
        1,
    ]

    row_codes = row_code_raw.map(
        lambda value: _extract_code(
            value,
            digits=row_digits,
        )
    )

    row_mask = (
        row_codes.notna()
    )

    matrix_columns: list[object] = []
    column_codes: list[str] = []
    column_names: list[str] = []

    for column in raw.columns:
        code = _extract_code(
            column,
            digits=column_digits,
        )

        if code is None:
            continue

        matrix_columns.append(
            column
        )

        column_codes.append(
            code
        )

        column_names.append(
            _extract_header_name(
                column,
                digits=column_digits,
            )
        )

    values = (
        raw
        .loc[
            row_mask,
            matrix_columns,
        ]
        .apply(
            pd.to_numeric,
            errors="coerce",
        )
        .copy()
    )

    parsed_row_codes = (
        row_codes.loc[
            row_mask
        ]
        .tolist()
    )

    values.index = (
        parsed_row_codes
    )

    values.columns = (
        column_codes
    )

    if (
        values.shape
        != expected_shape
    ):
        raise ValueError(
            "Unexpected matrix shape: "
            f"expected {expected_shape}, "
            f"got {values.shape}"
        )

    if values.isna().any().any():
        raise ValueError(
            "Parsed matrix contains missing "
            "numeric values."
        )

    if values.index.has_duplicates:
        raise ValueError(
            "Duplicate row codes found."
        )

    if values.columns.has_duplicates:
        raise ValueError(
            "Duplicate column codes found."
        )

    row_labels = pd.DataFrame(
        {
            "code": (
                parsed_row_codes
            ),
            "name": (
                row_name_raw
                .loc[row_mask]
                .astype(str)
                .str.strip()
                .tolist()
            ),
        }
    )

    column_labels = pd.DataFrame(
        {
            "code": column_codes,
            "name": column_names,
        }
    )

    return _ParsedMatrix(
        values=values.astype(
            float
        ),
        row_labels=row_labels,
        column_labels=column_labels,
    )


def _read_matrix_sheet(
    path: Path,
    *,
    sheet_name: str,
    row_digits: int,
    column_digits: int,
    expected_shape: tuple[int, int],
) -> _ParsedMatrix:
    raw = pd.read_excel(
        path,
        sheet_name=sheet_name,
        skiprows=3,
        engine="xlrd",
    )

    return _parse_matrix_frame(
        raw,
        row_digits=row_digits,
        column_digits=column_digits,
        expected_shape=expected_shape,
    )


def _same_codes(
    left: pd.Index,
    right: pd.Index,
) -> bool:
    return set(left) == set(
        right
    )


def parse_ibge_workbook(
    path: str | Path,
) -> IOTables:
    path = Path(
        path
    )

    if not path.exists():
        raise FileNotFoundError(
            path
        )

    # Table 11:
    # national input coefficients
    # products x sectors
    bn = _read_matrix_sheet(
        path,
        sheet_name="11",
        row_digits=5,
        column_digits=4,
        expected_shape=(
            127,
            67,
        ),
    )

    # Table 13:
    # sector participation /
    # market-share matrix
    # sectors x products
    d = _read_matrix_sheet(
        path,
        sheet_name="13",
        row_digits=4,
        column_digits=5,
        expected_shape=(
            67,
            127,
        ),
    )

    # Table 14:
    # official intersectoral
    # technical coefficients
    a = _read_matrix_sheet(
        path,
        sheet_name="14",
        row_digits=4,
        column_digits=4,
        expected_shape=(
            67,
            67,
        ),
    )

    # Table 15:
    # official Leontief inverse
    l = _read_matrix_sheet(
        path,
        sheet_name="15",
        row_digits=4,
        column_digits=4,
        expected_shape=(
            67,
            67,
        ),
    )

    products = (
        bn.row_labels
        .drop_duplicates(
            "code"
        )
        .reset_index(
            drop=True
        )
    )

    sectors = (
        bn.column_labels
        .drop_duplicates(
            "code"
        )
        .reset_index(
            drop=True
        )
    )

    product_codes = (
        products["code"]
        .tolist()
    )

    sector_codes = (
        sectors["code"]
        .tolist()
    )

    final_demand_products = (
        _read_final_demand(
            path
        )
    )

    # --------------------------------------------------
    # Structural validation
    # --------------------------------------------------

    if not _same_codes(
        bn.values.columns,
        d.values.index,
    ):
        raise ValueError(
            "Sector codes differ between "
            "Bn and D."
        )

    if not _same_codes(
        bn.values.index,
        d.values.columns,
    ):
        raise ValueError(
            "Product codes differ between "
            "Bn and D."
        )

    for matrix_name, matrix in {
        "A_official": a.values,
        "L_official": l.values,
    }.items():
        if not _same_codes(
            matrix.index,
            pd.Index(
                sector_codes
            ),
        ):
            raise ValueError(
                f"{matrix_name} has unexpected "
                "sector rows."
            )

        if not _same_codes(
            matrix.columns,
            pd.Index(
                sector_codes
            ),
        ):
            raise ValueError(
                f"{matrix_name} has unexpected "
                "sector columns."
            )

    if set(
        final_demand_products.index
    ) != set(
        product_codes
    ):
        raise ValueError(
            "Product codes differ between "
            "final demand and Bn."
        )

    # --------------------------------------------------
    # Canonical ordering
    # --------------------------------------------------

    Bn = bn.values.reindex(
        index=product_codes,
        columns=sector_codes,
    )

    D = d.values.reindex(
        index=sector_codes,
        columns=product_codes,
    )

    A_official = a.values.reindex(
        index=sector_codes,
        columns=sector_codes,
    )

    L_official = l.values.reindex(
        index=sector_codes,
        columns=sector_codes,
    )

    Bn.index.name = (
        "product_code"
    )
    Bn.columns.name = (
        "sector_code"
    )

    D.index.name = (
        "sector_code"
    )
    D.columns.name = (
        "product_code"
    )

    final_demand_by_product = (
        final_demand_products
        .reindex(
            product_codes
        )
    )

    final_demand_by_sector = (
        D
        @ final_demand_by_product
    )
    
    final_demand_by_sector.index.name = (
        "sector_code"
    )

    for matrix in (
        A_official,
        L_official,
    ):
        matrix.index.name = (
            "sector_code"
        )
        matrix.columns.name = (
            "sector_code"
        )

    return IOTables(
        Bn=Bn,
        D=D,
        A_official=A_official,
        L_official=L_official,
    
        final_demand_by_product=(
            final_demand_by_product
        ),
    
        final_demand_by_sector=(
            final_demand_by_sector
        ),
    
        sectors=sectors,
        products=products,
    )


def _parse_final_demand_frame(
    raw: pd.DataFrame,
    *,
    expected_rows: int = 127,
) -> pd.DataFrame:
    row_codes = (
        raw.iloc[:, 0]
        .map(
            lambda value: _extract_code(
                value,
                digits=5,
            )
        )
    )

    row_mask = (
        row_codes.notna()
    )

    normalized_columns = {
        _normalize_header(
            column
        ): column
        for column in raw.columns
    }

    missing = (
        set(
            FINAL_DEMAND_COLUMNS
        )
        - set(
            normalized_columns
        )
    )

    if missing:
        raise ValueError(
            "Missing final-demand columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    selected = {}

    for (
        original_name,
        canonical_name,
    ) in FINAL_DEMAND_COLUMNS.items():
        source_column = (
            normalized_columns[
                original_name
            ]
        )

        selected[
            canonical_name
        ] = pd.to_numeric(
            raw.loc[
                row_mask,
                source_column,
            ],
            errors="coerce",
        ).to_numpy()

    result = pd.DataFrame(
        selected,
        index=(
            row_codes
            .loc[row_mask]
            .tolist()
        ),
    )

    result.index.name = (
        "product_code"
    )

    if (
        len(result)
        != expected_rows
    ):
        raise ValueError(
            "Unexpected number of product "
            "rows in final demand: "
            f"expected {expected_rows}, "
            f"got {len(result)}"
        )

    if result.index.has_duplicates:
        raise ValueError(
            "Duplicate product codes found "
            "in final demand."
        )

    if result.isna().any().any():
        raise ValueError(
            "Final-demand table contains "
            "missing numeric values."
        )

    component_columns = [
        "exports",
        "government_consumption",
        "npish_consumption",
        "household_consumption",
        "gross_fixed_capital_formation",
        "inventory_change",
    ]
    
    reconstructed_total = (
        result[
            component_columns
        ]
        .sum(axis=1)
    )
    
    if not np.allclose(
        reconstructed_total,
        result[
            "total_final_demand"
        ],
        atol=1e-6,
        rtol=0.0,
    ):
        raise ValueError(
            "Final-demand components do not "
            "sum to total final demand."
        )

    return result.astype(
        float
    )


def _read_final_demand(
    path: Path,
) -> pd.DataFrame:
    raw = pd.read_excel(
        path,
        sheet_name="03",
        skiprows=3,
        engine="xlrd",
    )

    return _parse_final_demand_frame(
        raw
    )
