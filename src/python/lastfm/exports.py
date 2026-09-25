from dataclasses import dataclass
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path("data/processed/lastfm/lastfm.duckdb")

DEFAULT_EXPORT_DIR = Path("data/processed/lastfm/public")


@dataclass(frozen=True)
class ExportSpec:
    filename: str
    query: str


PUBLIC_EXPORTS = {
    "overview": ExportSpec(
        filename="overview.parquet",
        query="""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM fact_scrobble
                ) AS scrobbles,

                (
                    SELECT COUNT(*)
                    FROM dim_artist
                ) AS artists,

                (
                    SELECT COUNT(*)
                    FROM dim_track
                ) AS tracks,

                (
                    SELECT COUNT(*)
                    FROM dim_album
                ) AS albums,

                (
                    SELECT COUNT(*)
                    FROM mart_listening_sessions
                ) AS sessions,

                (
                    SELECT MIN(scrobbled_at_local)
                    FROM fact_scrobble
                ) AS first_observed_at,

                (
                    SELECT MAX(scrobbled_at_local)
                    FROM fact_scrobble
                ) AS last_observed_at
        """,
    ),
    "genre_yearly": ExportSpec(
        filename="genre_yearly.parquet",
        query="""
            SELECT *
            FROM mart_genre_yearly
            ORDER BY
                listening_year,
                weighted_scrobbles DESC,
                canonical_genre
        """,
    ),
    "genre_monthly": ExportSpec(
        filename="genre_monthly.parquet",
        query="""
            SELECT *
            FROM mart_genre_monthly
            ORDER BY
                month_start,
                weighted_scrobbles DESC,
                canonical_genre
        """,
    ),
    "genre_seasonality": ExportSpec(
        filename="genre_seasonality.parquet",
        query="""
            SELECT *
            FROM mart_genre_seasonality
            ORDER BY
                season_order,
                canonical_genre
        """,
    ),
    "genre_seasonality_yearly": ExportSpec(
        filename="genre_seasonality_yearly.parquet",
        query="""
            SELECT *
            FROM mart_genre_seasonality_yearly
            ORDER BY
                season_year,
                season_order,
                canonical_genre
        """,
    ),
    "artist_yearly": ExportSpec(
        filename="artist_yearly.parquet",
        query="""
            SELECT *
            FROM mart_artist_yearly
            ORDER BY
                listening_year,
                artist_rank,
                artist_name
        """,
    ),
    "artist_lifecycle": ExportSpec(
        filename="artist_lifecycle.parquet",
        query="""
            SELECT *
            FROM mart_artist_lifecycle
            ORDER BY
                total_scrobbles DESC,
                artist_name
        """,
    ),
    "monthly_discovery": ExportSpec(
        filename="monthly_discovery.parquet",
        query="""
            SELECT *
            FROM mart_monthly_discovery
            ORDER BY
                month_start
        """,
    ),
    "listening_by_hour": ExportSpec(
        filename="listening_by_hour.parquet",
        query="""
            SELECT *
            FROM mart_listening_by_hour
            ORDER BY
                listening_hour
        """,
    ),
    "listening_by_hour_temporal": ExportSpec(
        filename="listening_by_hour_temporal.parquet",
        query="""
            SELECT *
            FROM mart_listening_by_hour_temporal
            ORDER BY
                month_start,
                weekday_iso,
                listening_hour
        """,
    ),
    "listening_by_decade": ExportSpec(
        filename="listening_by_decade.parquet",
        query="""
            SELECT *
            FROM mart_listening_by_decade
            ORDER BY release_decade
        """,
    ),
    "listening_by_decade_yearly": ExportSpec(
        filename="listening_by_decade_yearly.parquet",
        query="""
            SELECT *
            FROM mart_listening_by_decade_yearly
            ORDER BY
                listening_year,
                release_decade
        """,
    ),
    "listening_sessions": ExportSpec(
        filename="listening_sessions.parquet",
        query="""
            SELECT
                CAST(
                    DATE_TRUNC(
                        'month',
                        session_start_at
                    )
                    AS DATE
                ) AS month_start,

                EXTRACT(
                    HOUR FROM session_start_at
                ) AS start_hour,

                session_span_seconds,
                session_span_minutes,
                scrobble_count,
                distinct_artists,
                distinct_tracks,
                distinct_albums

            FROM mart_listening_sessions

            ORDER BY
                month_start,
                start_hour
        """,
    ),
}


def _quote_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def export_dashboard_data(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_EXPORT_DIR
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    exported: list[Path] = []

    with duckdb.connect(str(db_path), read_only=True) as connection:
        for spec in PUBLIC_EXPORTS.values():
            output_path = output_dir / spec.filename

            quoted_path = _quote_path(output_path)

            connection.execute(
                f"""
                COPY (
                    {spec.query}
                )
                TO '{quoted_path}'
                (
                    FORMAT PARQUET,
                    COMPRESSION ZSTD
                )
                """
            )

            exported.append(output_path)

    return exported
