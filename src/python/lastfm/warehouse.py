import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from lastfm.models import Scrobble, parse_recent_tracks

DEFAULT_RAW_ROOT = Path("data/raw/lastfm")
DEFAULT_DB_PATH = Path("data/processed/lastfm/lastfm.duckdb")
DEFAULT_SQL_ROOT = Path("sql/lastfm")


@dataclass(frozen=True, slots=True)
class WarehouseBuildResult:
    complete_runs: int
    bronze_observations: int
    historical_observations: int
    now_playing_observations: int
    unique_scrobbles: int
    duplicates_removed: int


def iter_complete_runs(
    raw_root: Path = DEFAULT_RAW_ROOT,
) -> Iterator[Path]:
    runs_root = raw_root / "runs"

    if not runs_root.exists():
        return

    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        if (run_dir / "manifest.json").exists():
            yield run_dir


def _load_manifest(
    run_dir: Path,
) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def _iter_run_observations(
    run_dir: Path,
    *,
    raw_root: Path,
) -> Iterator[tuple]:
    manifest = _load_manifest(run_dir)

    run_id = run_dir.name

    ingested_at = datetime.fromisoformat(manifest["completed_at_utc"])

    for page_path in sorted(run_dir.glob("page_*.json")):
        page = int(page_path.stem.removeprefix("page_"))

        payload = json.loads(page_path.read_text(encoding="utf-8"))

        scrobbles = parse_recent_tracks(payload)

        for position, scrobble in enumerate(
            scrobbles,
            start=1,
        ):
            yield _bronze_row(
                scrobble,
                run_id=run_id,
                page=page,
                position=position,
                ingested_at=ingested_at,
                source_file=str(page_path.relative_to(raw_root)),
            )


def _bronze_row(
    scrobble: Scrobble,
    *,
    run_id: str,
    page: int,
    position: int,
    ingested_at: datetime,
    source_file: str,
) -> tuple:
    observation_id = f"{run_id}:{page:05d}:{position:04d}"

    return (
        observation_id,
        run_id,
        page,
        position,
        scrobble.artist,
        scrobble.track,
        scrobble.album,
        scrobble.artist_mbid,
        scrobble.track_mbid,
        scrobble.album_mbid,
        scrobble.scrobbled_at,
        scrobble.scrobbled_at_uts,
        scrobble.track_url,
        scrobble.is_now_playing,
        ingested_at,
        source_file,
    )


def _create_bronze_table(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE
            bronze_scrobbles
        (
            observation_id VARCHAR PRIMARY KEY,
            run_id VARCHAR NOT NULL,
            source_page INTEGER NOT NULL,
            source_position INTEGER NOT NULL,
            artist VARCHAR NOT NULL,
            track VARCHAR NOT NULL,
            album VARCHAR,
            artist_mbid VARCHAR,
            track_mbid VARCHAR,
            album_mbid VARCHAR,
            scrobbled_at TIMESTAMPTZ,
            scrobbled_at_uts BIGINT,
            track_url VARCHAR,
            is_now_playing BOOLEAN NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            source_file VARCHAR NOT NULL
        )
        """
    )


def build_warehouse(
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    db_path: Path = DEFAULT_DB_PATH,
    sql_root: Path = DEFAULT_SQL_ROOT,
) -> WarehouseBuildResult:
    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_dirs = list(iter_complete_runs(raw_root))

    rows = [
        row
        for run_dir in run_dirs
        for row in _iter_run_observations(
            run_dir,
            raw_root=raw_root,
        )
    ]

    with duckdb.connect(str(db_path)) as connection:
        _create_bronze_table(connection)

        if rows:
            connection.executemany(
                """
                INSERT INTO bronze_scrobbles
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )

        staging_sql = (sql_root / "001_stg_scrobbles.sql").read_text(encoding="utf-8")

        connection.execute(staging_sql)

        bronze_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM bronze_scrobbles
            """
        ).fetchone()[0]

        historical_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM bronze_scrobbles
                WHERE NOT is_now_playing
                """
        ).fetchone()[0]

        now_playing_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM bronze_scrobbles
                WHERE is_now_playing
                """
        ).fetchone()[0]

        unique_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM stg_scrobbles
                """
        ).fetchone()[0]

    return WarehouseBuildResult(
        complete_runs=len(run_dirs),
        bronze_observations=(bronze_count),
        historical_observations=(historical_count),
        now_playing_observations=(now_playing_count),
        unique_scrobbles=(unique_count),
        duplicates_removed=(historical_count - unique_count),
    )
