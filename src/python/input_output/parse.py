from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class IOTables:
    """
    Parsed IBGE input-output tables.

    Dimensions for the 2015 level-67 release:

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
    """

    Bn: pd.DataFrame
    D: pd.DataFrame
    A_official: pd.DataFrame
    L_official: pd.DataFrame

    sectors: pd.DataFrame
    products: pd.DataFrame


@dataclass(frozen=True)
class _ParsedMatrix:
    values: pd.DataFrame
    row_labels: pd.DataFrame
    column_labels: pd.DataFrame


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
        sectors=sectors,
        products=products,
    )
