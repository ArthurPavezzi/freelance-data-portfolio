from pathlib import Path

from lastfm.exports import DEFAULT_EXPORT_DIR, export_dashboard_data
from lastfm.warehouse import (
    DEFAULT_DB_PATH,
    DEFAULT_RAW_ROOT,
    DEFAULT_SQL_ROOT,
    WarehouseBuildResult,
    build_analytics,
    build_warehouse,
)


def refresh_dashboard_data(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    sql_root: Path = DEFAULT_SQL_ROOT,
    output_dir: Path = DEFAULT_EXPORT_DIR,
) -> list[Path]:
    """Rebuild analytics marts and refresh public dashboard exports."""
    build_analytics(db_path=db_path, sql_root=sql_root)

    return export_dashboard_data(db_path=db_path, output_dir=output_dir)


def full_refresh(
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    db_path: Path = DEFAULT_DB_PATH,
    sql_root: Path = DEFAULT_SQL_ROOT,
    output_dir: Path = DEFAULT_EXPORT_DIR,
) -> tuple[WarehouseBuildResult, list[Path]]:
    """Refresh raw layers, analytics marts, and public dashboard exports."""
    build_result = build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=sql_root)

    exported = export_dashboard_data(db_path=db_path, output_dir=output_dir)

    return build_result, exported
