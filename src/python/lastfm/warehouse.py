import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

import duckdb

from lastfm.models import Scrobble, parse_recent_tracks
from lastfm.tags import parse_album_tags, parse_artist_tags
from lastfm.taxonomy_warehouse import load_tag_taxonomy

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


def iter_complete_runs(raw_root: Path = DEFAULT_RAW_ROOT) -> Iterator[Path]:
    runs_root = raw_root / "runs"

    if not runs_root.exists():
        return

    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        if (run_dir / "manifest.json").exists():
            yield run_dir


def _load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def _iter_run_observations(run_dir: Path, *, raw_root: Path) -> Iterator[tuple]:
    manifest = _load_manifest(run_dir)

    run_id = run_dir.name

    ingested_at = datetime.fromisoformat(manifest["completed_at_utc"])

    for page_path in sorted(run_dir.glob("page_*.json")):
        page = int(page_path.stem.removeprefix("page_"))

        payload = json.loads(page_path.read_text(encoding="utf-8"))

        scrobbles = parse_recent_tracks(payload)

        for position, scrobble in enumerate(scrobbles, start=1):
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


def _create_bronze_table(connection: duckdb.DuckDBPyConnection) -> None:
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


def _create_album_tag_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE
            album_tag_enrichment
        (
            album_id VARCHAR PRIMARY KEY,
            status VARCHAR NOT NULL,
            requested_artist VARCHAR NOT NULL,
            requested_album VARCHAR NOT NULL,
            album_mbid VARCHAR,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            error_code INTEGER,
            error_message VARCHAR,
            tag_count INTEGER NOT NULL,
            cache_file VARCHAR NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE
            bronze_album_tags
        (
            album_id VARCHAR NOT NULL,
            tag_rank INTEGER NOT NULL,
            tag_raw VARCHAR NOT NULL,
            tag_norm VARCHAR NOT NULL,
            tag_weight INTEGER NOT NULL,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            cache_file VARCHAR NOT NULL,

            PRIMARY KEY (
                album_id,
                tag_rank
            )
        )
        """
    )


def _load_album_tag_cache(connection: duckdb.DuckDBPyConnection, *, raw_root: Path) -> None:
    enrichment_root = raw_root / "enrichment" / "album_tags"

    _create_album_tag_tables(connection)

    if not enrichment_root.exists():
        return

    enrichment_rows = []
    tag_rows = []

    for path in sorted(enrichment_root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))

        album_id = record["album_id"]

        status = record["status"]

        fetched_at = datetime.fromisoformat(record["fetched_at_utc"])

        if status == "ok":
            tags = parse_album_tags(album_id, record.get("response", {}))
        else:
            tags = []

        relative_path = str(path.relative_to(raw_root))

        enrichment_rows.append(
            (
                album_id,
                status,
                record["requested_artist"],
                record["requested_album"],
                record.get("album_mbid"),
                fetched_at,
                record.get("error_code"),
                record.get("error_message"),
                len(tags),
                relative_path,
            )
        )

        tag_rows.extend(
            (
                tag.album_id,
                tag.rank,
                tag.tag_raw,
                tag.tag_norm,
                tag.weight,
                fetched_at,
                relative_path,
            )
            for tag in tags
        )

    if enrichment_rows:
        connection.executemany(
            """
            INSERT INTO
                album_tag_enrichment
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            enrichment_rows,
        )

    if tag_rows:
        connection.executemany(
            """
            INSERT INTO
                bronze_album_tags
            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            tag_rows,
        )


def _create_artist_tag_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE
            artist_tag_enrichment
        (
            artist_id VARCHAR PRIMARY KEY,
            status VARCHAR NOT NULL,
            requested_artist VARCHAR NOT NULL,
            artist_mbid VARCHAR,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            error_code INTEGER,
            error_message VARCHAR,
            tag_count INTEGER NOT NULL,
            cache_file VARCHAR NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE
            bronze_artist_tags
        (
            artist_id VARCHAR NOT NULL,
            tag_rank INTEGER NOT NULL,
            tag_raw VARCHAR NOT NULL,
            tag_norm VARCHAR NOT NULL,
            tag_weight INTEGER NOT NULL,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            cache_file VARCHAR NOT NULL,

            PRIMARY KEY (
                artist_id,
                tag_rank
            )
        )
        """
    )


def _load_artist_tag_cache(connection: duckdb.DuckDBPyConnection, *, raw_root: Path) -> None:
    enrichment_root = raw_root / "enrichment" / "artist_tags"

    _create_artist_tag_tables(connection)

    if not enrichment_root.exists():
        return

    enrichment_rows = []
    tag_rows = []

    for path in sorted(enrichment_root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))

        artist_id = record["artist_id"]

        status = record["status"]

        fetched_at = datetime.fromisoformat(record["fetched_at_utc"])

        if status == "ok":
            tags = parse_artist_tags(artist_id, record.get("response", {}))
        else:
            tags = []

        relative_path = str(path.relative_to(raw_root))

        enrichment_rows.append(
            (
                artist_id,
                status,
                record["requested_artist"],
                record.get("artist_mbid"),
                fetched_at,
                record.get("error_code"),
                record.get("error_message"),
                len(tags),
                relative_path,
            )
        )

        tag_rows.extend(
            (
                tag.artist_id,
                tag.rank,
                tag.tag_raw,
                tag.tag_norm,
                tag.weight,
                fetched_at,
                relative_path,
            )
            for tag in tags
        )

    if enrichment_rows:
        connection.executemany(
            """
            INSERT INTO
                artist_tag_enrichment
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            enrichment_rows,
        )

    if tag_rows:
        connection.executemany(
            """
            INSERT INTO
                bronze_artist_tags
            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            tag_rows,
        )


def refresh_raw_layers(
    *, raw_root: Path = DEFAULT_RAW_ROOT, db_path: Path = DEFAULT_DB_PATH
) -> int:
    """Refresh DuckDB source layers from raw JSON and curated taxonomy inputs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    total_start = perf_counter()

    start = perf_counter()

    run_dirs = list(iter_complete_runs(raw_root))

    rows = [
        row for run_dir in run_dirs for row in _iter_run_observations(run_dir, raw_root=raw_root)
    ]

    print("scrobble raw load:", round(perf_counter() - start, 2), "s")

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

        start = perf_counter()

        _load_album_tag_cache(connection, raw_root=raw_root)

        print("album tag cache:", round(perf_counter() - start, 2), "s")

        start = perf_counter()

        _load_album_release_date_cache(connection, raw_root=raw_root)

        print("album release date cache:", round(perf_counter() - start, 2), "s")

        start = perf_counter()

        start = perf_counter()

        _load_artist_tag_cache(connection, raw_root=raw_root)

        print("artist tag cache:", round(perf_counter() - start, 2), "s")

        start = perf_counter()

        load_tag_taxonomy(connection, raw_root=raw_root)

        print("tag taxonomy:", round(perf_counter() - start, 2), "s")

    print("raw layers total:", round(perf_counter() - total_start, 2), "s")

    return len(run_dirs)


def build_analytics(*, db_path: Path = DEFAULT_DB_PATH, sql_root: Path = DEFAULT_SQL_ROOT) -> None:
    """Rebuild SQL transformation and analytics layers from existing source tables."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"DuckDB warehouse does not exist: {db_path}. "
            "Run refresh_raw_layers() or build_warehouse() first."
        )

    sql_paths = sorted(sql_root.glob("*.sql"))

    start = perf_counter()

    with duckdb.connect(str(db_path)) as connection:
        for sql_path in sql_paths:
            sql = sql_path.read_text(encoding="utf-8")

            connection.execute(sql)

    print(
        "sql transformations:", round(perf_counter() - start, 2), "s", f"({len(sql_paths)} files)"
    )


def _collect_warehouse_build_result(*, db_path: Path, complete_runs: int) -> WarehouseBuildResult:
    with duckdb.connect(str(db_path), read_only=True) as connection:
        result = connection.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM bronze_scrobbles
                ) AS bronze_observations,

                (
                    SELECT COUNT(*)
                    FROM bronze_scrobbles
                    WHERE NOT is_now_playing
                ) AS historical_observations,

                (
                    SELECT COUNT(*)
                    FROM bronze_scrobbles
                    WHERE is_now_playing
                ) AS now_playing_observations,

                (
                    SELECT COUNT(*)
                    FROM stg_scrobbles
                ) AS unique_scrobbles
            """
        ).fetchone()

    if result is None:
        raise RuntimeError("Warehouse metrics query returned no result.")

    (bronze_count, historical_count, now_playing_count, unique_count) = (
        int(value) for value in result
    )

    return WarehouseBuildResult(
        complete_runs=complete_runs,
        bronze_observations=bronze_count,
        historical_observations=historical_count,
        now_playing_observations=now_playing_count,
        unique_scrobbles=unique_count,
        duplicates_removed=(historical_count - unique_count),
    )


def build_warehouse(
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    db_path: Path = DEFAULT_DB_PATH,
    sql_root: Path = DEFAULT_SQL_ROOT,
) -> WarehouseBuildResult:
    """Fully refresh source layers and rebuild all analytics transformations."""
    complete_runs = refresh_raw_layers(raw_root=raw_root, db_path=db_path)

    build_analytics(db_path=db_path, sql_root=sql_root)

    return _collect_warehouse_build_result(db_path=db_path, complete_runs=complete_runs)


def _create_album_release_date_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE
            album_release_date_enrichment
        (
            album_id VARCHAR PRIMARY KEY,
            status VARCHAR NOT NULL,
            requested_artist VARCHAR NOT NULL,
            requested_album VARCHAR NOT NULL,
            album_mbid VARCHAR,
            scrobble_count BIGINT NOT NULL,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            error_code INTEGER,
            error_message VARCHAR,
            retryable BOOLEAN,
            cache_file VARCHAR NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE
            bronze_album_release_dates
        (
            album_id VARCHAR PRIMARY KEY,
            album_mbid VARCHAR,
            musicbrainz_entity_type VARCHAR,
            resolution_method VARCHAR,
            release_group_mbid VARCHAR,
            first_release_date VARCHAR,
            first_release_year INTEGER NOT NULL,
            matched_title VARCHAR,
            matched_primary_type VARCHAR,
            match_score INTEGER,
            fetched_at_utc TIMESTAMPTZ NOT NULL,
            cache_file VARCHAR NOT NULL
        )
        """
    )


def _load_album_release_date_cache(
    connection: duckdb.DuckDBPyConnection, *, raw_root: Path
) -> None:
    enrichment_root = raw_root / "enrichment" / "album_release_dates"

    _create_album_release_date_tables(connection)

    if not enrichment_root.exists():
        return

    enrichment_rows = []
    release_date_rows = []

    for path in sorted(enrichment_root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))

        album_id = record["album_id"]

        status = record["status"]

        fetched_at = datetime.fromisoformat(record["fetched_at_utc"])

        relative_path = str(path.relative_to(raw_root))

        enrichment_rows.append(
            (
                album_id,
                status,
                record["requested_artist"],
                record["requested_album"],
                record.get("album_mbid"),
                int(record.get("scrobble_count", 0)),
                fetched_at,
                record.get("error_code"),
                record.get("error_message"),
                record.get("retryable"),
                relative_path,
            )
        )

        first_release_year = record.get("first_release_year")

        if status == "ok" and first_release_year is not None:
            release_date_rows.append(
                (
                    album_id,
                    record.get("album_mbid"),
                    record.get("musicbrainz_entity_type"),
                    record.get("resolution_method"),
                    record.get("release_group_mbid"),
                    record.get("first_release_date"),
                    int(first_release_year),
                    record.get("matched_title"),
                    record.get("matched_primary_type"),
                    record.get("match_score"),
                    fetched_at,
                    relative_path,
                )
            )

    if enrichment_rows:
        connection.executemany(
            """
            INSERT INTO
                album_release_date_enrichment
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            enrichment_rows,
        )

    if release_date_rows:
        connection.executemany(
            """
            INSERT INTO
                bronze_album_release_dates
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            release_date_rows,
        )
