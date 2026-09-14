import json
from pathlib import Path

import duckdb
from lastfm.warehouse import build_warehouse


def historical_track(
    *,
    artist: str,
    track: str,
    album: str,
    uts: int,
) -> dict:
    return {
        "artist": {
            "mbid": "",
            "#text": artist,
        },
        "album": {
            "mbid": "",
            "#text": album,
        },
        "mbid": "",
        "name": track,
        "url": "https://example.com",
        "date": {
            "uts": str(uts),
            "#text": "",
        },
    }


def now_playing_track() -> dict:
    return {
        "artist": {
            "mbid": "",
            "#text": "Current Artist",
        },
        "album": {
            "mbid": "",
            "#text": "Current Album",
        },
        "mbid": "",
        "name": "Current Track",
        "url": "https://example.com",
        "@attr": {
            "nowplaying": "true",
        },
    }


def write_run(
    raw_root: Path,
    *,
    run_id: str,
    tracks: list[dict],
    completed_at: str,
    complete: bool = True,
) -> None:
    run_dir = raw_root / "runs" / run_id

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "recenttracks": {
            "track": tracks,
            "@attr": {
                "user": "test-user",
                "page": "1",
                "perPage": "200",
                "totalPages": "1",
                "total": str(sum("date" in track for track in tracks)),
            },
        }
    }

    (run_dir / "page_00001.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    if complete:
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "completed_at_utc": (completed_at),
                }
            ),
            encoding="utf-8",
        )


def test_build_warehouse_preserves_bronze_and_deduplicates_staging(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=100,
            ),
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=200,
            ),
            now_playing_track(),
        ],
    )

    write_run(
        raw_root,
        run_id="run-2",
        completed_at=("2026-09-14T21:00:00+00:00"),
        tracks=[
            # Deliberate overlap.
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=200,
            ),
            historical_track(
                artist="Artist C",
                track="Track C",
                album="Album C",
                uts=300,
            ),
        ],
    )

    result = build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    assert result.complete_runs == 2
    assert result.bronze_observations == 5
    assert result.historical_observations == 4
    assert result.now_playing_observations == 1
    assert result.unique_scrobbles == 3
    assert result.duplicates_removed == 1

    with duckdb.connect(str(db_path)) as connection:
        uts = [
            row[0]
            for row in connection.execute(
                """
                SELECT scrobbled_at_uts
                FROM stg_scrobbles
                ORDER BY scrobbled_at_uts
                """
            ).fetchall()
        ]

    assert uts == [
        100,
        200,
        300,
    ]


def test_build_warehouse_ignores_incomplete_runs(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="incomplete-run",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist",
                track="Track",
                album="Album",
                uts=100,
            )
        ],
        complete=False,
    )

    result = build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    assert result.complete_runs == 0
    assert result.bronze_observations == 0
    assert result.historical_observations == 0
    assert result.now_playing_observations == 0
    assert result.unique_scrobbles == 0
    assert result.duplicates_removed == 0


def test_star_schema_has_no_orphan_keys(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_757_870_000,
            ),
            historical_track(
                artist="Artist B",
                track="Track B",
                album="",
                uts=1_757_870_100,
            ),
        ],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        artist_orphans = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble f
                LEFT JOIN dim_artist a
                    USING (artist_id)
                WHERE a.artist_id IS NULL
                """
        ).fetchone()[0]

        track_orphans = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble f
                LEFT JOIN dim_track t
                    USING (track_id)
                WHERE t.track_id IS NULL
                """
        ).fetchone()[0]

        album_orphans = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble f
                LEFT JOIN dim_album a
                    USING (album_id)
                WHERE
                    f.album_id IS NOT NULL
                    AND a.album_id IS NULL
                """
        ).fetchone()[0]

    assert artist_orphans == 0
    assert track_orphans == 0
    assert album_orphans == 0


def test_fact_scrobble_matches_staging_count(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=100,
            ),
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=200,
            ),
        ],
    )

    write_run(
        raw_root,
        run_id="run-2",
        completed_at=("2026-09-14T21:00:00+00:00"),
        tracks=[
            # Intentional overlap with run-1.
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=200,
            ),
            historical_track(
                artist="Artist C",
                track="Track C",
                album="Album C",
                uts=300,
            ),
        ],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        staging_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM stg_scrobbles
                """
        ).fetchone()[0]

        fact_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble
                """
        ).fetchone()[0]

    assert staging_count == 3
    assert fact_count == 3
    assert fact_count == staging_count
