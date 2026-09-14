from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CoreOutputPaths:
    technical_coefficients: Path
    leontief_inverse: Path
    sector_linkages: Path


def _matrix_for_export(
    matrix: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert a sector-by-sector matrix into a portable
    DataFrame with the row sector code as an explicit column.
    """
    result = matrix.copy()

    result.index.name = "sector_code"

    return result.reset_index()


def write_core_outputs(
    *,
    technical_coefficients: pd.DataFrame,
    leontief_inverse: pd.DataFrame,
    sector_linkages: pd.DataFrame,
    output_dir: Path | str = Path("data/processed/input_output"),
) -> CoreOutputPaths:
    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    technical_path = output_dir / "technical_coefficients.parquet"

    leontief_path = output_dir / "leontief_inverse.parquet"

    linkages_path = output_dir / "sector_linkages.parquet"

    _matrix_for_export(technical_coefficients).to_parquet(
        technical_path,
        index=False,
    )

    _matrix_for_export(leontief_inverse).to_parquet(
        leontief_path,
        index=False,
    )

    sector_linkages.to_parquet(
        linkages_path,
        index=False,
    )

    return CoreOutputPaths(
        technical_coefficients=technical_path,
        leontief_inverse=leontief_path,
        sector_linkages=linkages_path,
    )
