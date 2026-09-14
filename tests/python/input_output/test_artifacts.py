from pathlib import Path

import pandas as pd

from input_output.artifacts import (
    write_core_outputs,
)


def _matrix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [1.0, 0.2],
            [0.3, 1.1],
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


def _linkages() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sector_code": [
                "S1",
                "S2",
            ],
            "sector_name": [
                "Sector 1",
                "Sector 2",
            ],
            "forward_linkage": [
                1.2,
                0.8,
            ],
            "backward_linkage": [
                1.1,
                0.9,
            ],
            "sector_type": [
                "III",
                "I",
            ],
            "is_key_sector": [
                True,
                False,
            ],
        }
    )


def test_write_core_outputs_creates_files(
    tmp_path: Path,
) -> None:
    paths = write_core_outputs(
        technical_coefficients=_matrix(),
        leontief_inverse=_matrix(),
        sector_linkages=_linkages(),
        output_dir=tmp_path,
    )

    assert (
        paths.technical_coefficients.exists()
    )

    assert (
        paths.leontief_inverse.exists()
    )

    assert (
        paths.sector_linkages.exists()
    )


def test_written_outputs_roundtrip(
    tmp_path: Path,
) -> None:
    A = _matrix()
    L = _matrix()
    linkages = _linkages()

    paths = write_core_outputs(
        technical_coefficients=A,
        leontief_inverse=L,
        sector_linkages=linkages,
        output_dir=tmp_path,
    )

    stored_A = pd.read_parquet(
        paths.technical_coefficients
    )

    stored_L = pd.read_parquet(
        paths.leontief_inverse
    )

    stored_linkages = pd.read_parquet(
        paths.sector_linkages
    )

    assert (
        stored_A["sector_code"].tolist()
        == ["S1", "S2"]
    )

    assert (
        stored_L["sector_code"].tolist()
        == ["S1", "S2"]
    )

    pd.testing.assert_frame_equal(
        stored_A.drop(
            columns="sector_code"
        ),
        A.reset_index(
            drop=True
        ),
        check_names=False,
    )

    pd.testing.assert_frame_equal(
        stored_L.drop(
            columns="sector_code"
        ),
        L.reset_index(
            drop=True
        ),
        check_names=False,
    )

    pd.testing.assert_frame_equal(
        stored_linkages,
        linkages,
    )
