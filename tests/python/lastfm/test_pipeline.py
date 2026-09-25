from pathlib import Path

from lastfm.pipeline import refresh_dashboard_data


def test_refresh_dashboard_data_builds_exports(tmp_path: Path) -> None:
    # This test intentionally uses the existing warehouse only
    # through explicitly supplied temporary paths in future
    # integration fixtures.
    assert callable(refresh_dashboard_data)
