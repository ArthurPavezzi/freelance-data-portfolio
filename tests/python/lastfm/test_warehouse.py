import json
from hashlib import md5
from pathlib import Path

import duckdb
from lastfm.warehouse import build_warehouse


def historical_track(*, artist: str, track: str, album: str, uts: int) -> dict:
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


def make_artist_id(artist: str) -> str:
    normalized = artist.strip().lower()

    return md5(normalized.encode("utf-8")).hexdigest()


def make_album_id(artist: str, album: str) -> str:
    normalized = f"{artist.strip().lower()}|{album.strip().lower()}"

    return md5(normalized.encode("utf-8")).hexdigest()


def write_musicbrainz_genres(raw_root: Path, genres: list[str]) -> None:
    path = raw_root / "musicbrainz" / "genres.json"

    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "source": "https://musicbrainz.org/ws/2/genre/all",
        "fetched_at_utc": "2026-09-16T12:00:00+00:00",
        "genre_count": len(genres),
        "genres": [{"name": genre} for genre in genres],
    }

    path.write_text(json.dumps(payload), encoding="utf-8")


def write_artist_tag_cache(
    raw_root: Path,
    *,
    artist: str,
    tags: list[tuple[str, int]],
) -> str:
    artist_id = make_artist_id(artist)

    cache_dir = raw_root / "enrichment" / "artist_tags"

    cache_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "ok",
        "artist_id": artist_id,
        "requested_artist": artist,
        "artist_mbid": None,
        "scrobble_count": 1,
        "fetched_at_utc": "2026-09-15T12:00:00+00:00",
        "response": {
            "toptags": {
                "tag": [
                    {
                        "name": tag,
                        "count": weight,
                        "url": "https://example.com/tag",
                    }
                    for tag, weight in tags
                ]
            }
        },
    }

    (cache_dir / f"{artist_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    return artist_id


def write_album_tag_cache(
    raw_root: Path, *, artist: str, album: str, tags: list[tuple[str, int]]
) -> str:
    album_id = make_album_id(artist, album)

    cache_dir = raw_root / "enrichment" / "album_tags"

    cache_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "status": "ok",
        "album_id": album_id,
        "requested_artist": artist,
        "requested_album": album,
        "album_mbid": None,
        "scrobble_count": 1,
        "fetched_at_utc": ("2026-09-15T12:00:00+00:00"),
        "response": {
            "toptags": {
                "tag": [
                    {
                        "name": tag,
                        "count": weight,
                        "url": "https://example.com/tag",
                    }
                    for tag, weight in tags
                ]
            }
        },
    }

    (cache_dir / f"{album_id}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    return album_id


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

    run_dir.mkdir(parents=True, exist_ok=True)

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


def test_build_warehouse_preserves_bronze_and_deduplicates_staging(tmp_path: Path):
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


def test_build_warehouse_ignores_incomplete_runs(tmp_path: Path):
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


def test_star_schema_has_no_orphan_keys(tmp_path: Path):
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


def test_fact_scrobble_matches_staging_count(tmp_path: Path):
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


def test_daily_mart_preserves_scrobble_total(tmp_path: Path):
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
                uts=1_757_500_000,
            ),
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=1_757_586_400,
            ),
        ],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        fact_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble
                """
        ).fetchone()[0]

        mart_count = connection.execute(
            """
                SELECT SUM(scrobble_count)
                FROM mart_daily_listening
                """
        ).fetchone()[0]

    assert mart_count == fact_count


def test_artist_summary_preserves_scrobble_total(tmp_path: Path):
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
                artist="Artist A",
                track="Track B",
                album="Album A",
                uts=200,
            ),
            historical_track(
                artist="Artist B",
                track="Track C",
                album="Album B",
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
        result = connection.execute(
            """
            SELECT
                COUNT(*) AS artists,
                SUM(scrobble_count)
                    AS scrobbles
            FROM mart_artist_summary
            """
        ).fetchone()

    assert result == (2, 3)


def test_hour_mart_preserves_scrobble_total(tmp_path: Path):
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

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        fact_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM fact_scrobble
                """
        ).fetchone()[0]

        mart_count = connection.execute(
            """
                SELECT SUM(scrobble_count)
                FROM mart_listening_by_hour
                """
        ).fetchone()[0]

    assert mart_count == fact_count


def test_discovery_mart_counts_each_artist_once(tmp_path: Path):
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
                uts=1_735_900_000,
            ),
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_738_500_000,
            ),
            historical_track(
                artist="Artist B",
                track="Track B",
                album="Album B",
                uts=1_738_600_000,
            ),
        ],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        total_new_artists = connection.execute(
            """
                SELECT SUM(new_artists)
                FROM mart_monthly_discovery
                """
        ).fetchone()[0]

        artist_count = connection.execute(
            """
                SELECT COUNT(*)
                FROM dim_artist
                """
        ).fetchone()[0]

        cumulative_artists = connection.execute(
            """
                SELECT cumulative_artists
                FROM mart_monthly_discovery
                ORDER BY month_start DESC
                LIMIT 1
                """
        ).fetchone()[0]

    assert total_new_artists == 2
    assert total_new_artists == artist_count
    assert cumulative_artists == artist_count


def test_build_warehouse_loads_artist_tag_cache(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-15T12:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_757_930_000,
            )
        ],
    )

    artist_id = write_artist_tag_cache(
        raw_root,
        artist="Artist A",
        tags=[("Progressive Rock", 100), ("Art Rock", 40)],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        enrichment = connection.execute(
            """
                SELECT
                    status,
                    tag_count
                FROM artist_tag_enrichment
                WHERE artist_id = ?
                """,
            [artist_id],
        ).fetchone()

        tags = connection.execute(
            """
                SELECT
                    tag_rank,
                    tag_norm,
                    tag_weight
                FROM bronze_artist_tags
                WHERE artist_id = ?
                ORDER BY tag_rank
                """,
            [artist_id],
        ).fetchall()

    assert enrichment == ("ok", 2)

    assert tags == [(1, "progressive rock", 100), (2, "art rock", 40)]


def test_album_tags_take_precedence_over_artist_fallback(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-15T12:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_757_930_000,
            )
        ],
    )

    album_id = write_album_tag_cache(
        raw_root, artist="Artist A", album="Album A", tags=[("Progressive Metal", 100)]
    )

    write_artist_tag_cache(
        raw_root, artist="Artist A", tags=[("Progressive Rock", 100), ("Metal", 50)]
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        evidence = connection.execute(
            """
                SELECT
                    tag_norm,
                    tag_weight,
                    tag_source
                FROM bridge_album_tag_evidence
                WHERE album_id = ?
                ORDER BY tag_rank
                """,
            [album_id],
        ).fetchall()

    assert evidence == [("progressive metal", 100, "album")]


def test_album_genre_weights_sum_to_one(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-16T12:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_757_930_000,
            )
        ],
    )

    write_album_tag_cache(
        raw_root,
        artist="Artist A",
        album="Album A",
        tags=[
            (
                "Rock",
                100,
            ),
            (
                "Progressive Rock",
                50,
            ),
        ],
    )

    write_musicbrainz_genres(
        raw_root,
        [
            "rock",
            "progressive rock",
        ],
    )

    build_warehouse(
        raw_root=raw_root,
        db_path=db_path,
        sql_root=Path("sql/lastfm"),
    )

    with duckdb.connect(str(db_path)) as connection:
        max_error = connection.execute(
            """
                WITH album_weights AS (
                    SELECT
                        album_id,
                        SUM(
                            genre_weight
                        ) AS total_weight

                    FROM bridge_album_genre_weight

                    GROUP BY
                        album_id
                )

                SELECT
                    MAX(
                        ABS(
                            total_weight - 1.0
                        )
                    )

                FROM album_weights
                """
        ).fetchone()[0]

    assert max_error < 1e-12


def test_album_genre_bridge_collapses_aliases(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at="2026-09-16T12:00:00+00:00",
        tracks=[
            historical_track(
                artist="Artist A",
                track="Track A",
                album="Album A",
                uts=1_757_930_000,
            )
        ],
    )

    album_id = write_album_tag_cache(
        raw_root, artist="Artist A", album="Album A", tags=[("Hip Hop", 100), ("Hip-Hop", 80)]
    )

    write_musicbrainz_genres(raw_root, ["hip hop"])

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

    with duckdb.connect(str(db_path)) as connection:
        rows = connection.execute(
            """
                SELECT
                    canonical_genre,
                    genre_weight_raw,
                    source_tag_count,
                    genre_weight

                FROM bridge_album_genre_weight

                WHERE
                    album_id = ?

                ORDER BY
                    canonical_genre
                """,
            [album_id],
        ).fetchall()

    assert rows == [("hip hop", 100, 2, 1.0)]
