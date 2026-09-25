import json
from hashlib import md5
from pathlib import Path

import duckdb
from lastfm.warehouse import build_analytics, build_warehouse


def historical_track(*, artist: str, track: str, album: str, uts: int) -> dict:
    return {
        "artist": {"mbid": "", "#text": artist},
        "album": {"mbid": "", "#text": album},
        "mbid": "",
        "name": track,
        "url": "https://example.com",
        "date": {"uts": str(uts), "#text": ""},
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


def write_artist_tag_cache(raw_root: Path, *, artist: str, tags: list[tuple[str, int]]) -> str:
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
                    {"name": tag, "count": weight, "url": "https://example.com/tag"}
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

    cache_dir.mkdir(parents=True, exist_ok=True)

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
                    {"name": tag, "count": weight, "url": "https://example.com/tag"}
                    for tag, weight in tags
                ]
            }
        },
    }

    (cache_dir / f"{album_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    return album_id


def now_playing_track() -> dict:
    return {
        "artist": {"mbid": "", "#text": "Current Artist"},
        "album": {"mbid": "", "#text": "Current Album"},
        "mbid": "",
        "name": "Current Track",
        "url": "https://example.com",
        "@attr": {"nowplaying": "true"},
    }


def write_run(
    raw_root: Path, *, run_id: str, tracks: list[dict], completed_at: str, complete: bool = True
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

    (run_dir / "page_00001.json").write_text(json.dumps(payload), encoding="utf-8")

    if complete:
        (run_dir / "manifest.json").write_text(
            json.dumps({"completed_at_utc": (completed_at)}), encoding="utf-8"
        )


def test_build_warehouse_preserves_bronze_and_deduplicates_staging(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=100),
            historical_track(artist="Artist B", track="Track B", album="Album B", uts=200),
            now_playing_track(),
        ],
    )

    write_run(
        raw_root,
        run_id="run-2",
        completed_at=("2026-09-14T21:00:00+00:00"),
        tracks=[
            # Deliberate overlap.
            historical_track(artist="Artist B", track="Track B", album="Album B", uts=200),
            historical_track(artist="Artist C", track="Track C", album="Album C", uts=300),
        ],
    )

    result = build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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

    assert uts == [100, 200, 300]


def test_build_warehouse_ignores_incomplete_runs(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="incomplete-run",
        completed_at=("2026-09-14T20:00:00+00:00"),
        tracks=[historical_track(artist="Artist", track="Track", album="Album", uts=100)],
        complete=False,
    )

    result = build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
                artist="Artist A", track="Track A", album="Album A", uts=1_757_870_000
            ),
            historical_track(artist="Artist B", track="Track B", album="", uts=1_757_870_100),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=100),
            historical_track(artist="Artist B", track="Track B", album="Album B", uts=200),
        ],
    )

    write_run(
        raw_root,
        run_id="run-2",
        completed_at=("2026-09-14T21:00:00+00:00"),
        tracks=[
            # Intentional overlap with run-1.
            historical_track(artist="Artist B", track="Track B", album="Album B", uts=200),
            historical_track(artist="Artist C", track="Track C", album="Album C", uts=300),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
                artist="Artist A", track="Track A", album="Album A", uts=1_757_500_000
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_757_586_400
            ),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=100),
            historical_track(artist="Artist A", track="Track B", album="Album A", uts=200),
            historical_track(artist="Artist B", track="Track C", album="Album B", uts=300),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=100),
            historical_track(artist="Artist B", track="Track B", album="Album B", uts=200),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
                artist="Artist A", track="Track A", album="Album A", uts=1_735_900_000
            ),
            historical_track(
                artist="Artist A", track="Track A", album="Album A", uts=1_738_500_000
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_738_600_000
            ),
        ],
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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


def test_build_warehouse_loads_artist_tag_cache(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-15T12:00:00+00:00"),
        tracks=[
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000)
        ],
    )

    artist_id = write_artist_tag_cache(
        raw_root, artist="Artist A", tags=[("Progressive Rock", 100), ("Art Rock", 40)]
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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


def test_album_tags_take_precedence_over_artist_fallback(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-15T12:00:00+00:00"),
        tracks=[
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000)
        ],
    )

    album_id = write_album_tag_cache(
        raw_root, artist="Artist A", album="Album A", tags=[("Progressive Metal", 100)]
    )

    write_artist_tag_cache(
        raw_root, artist="Artist A", tags=[("Progressive Rock", 100), ("Metal", 50)]
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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


def test_album_genre_weights_sum_to_one(tmp_path: Path):
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-16T12:00:00+00:00"),
        tracks=[
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000)
        ],
    )

    write_album_tag_cache(
        raw_root, artist="Artist A", album="Album A", tags=[("Rock", 100), ("Progressive Rock", 50)]
    )

    write_musicbrainz_genres(raw_root, ["rock", "progressive rock"])

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

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
            historical_track(artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000)
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


def test_listening_session_span_precision(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"

    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE fact_scrobble (
                scrobble_id VARCHAR,
                artist_id VARCHAR,
                track_id VARCHAR,
                album_id VARCHAR,
                scrobbled_at_local TIMESTAMP,
                listening_date DATE
            )
            """
        )

        connection.execute(
            """
            INSERT INTO fact_scrobble
            VALUES
                (
                    's1',
                    'a1',
                    't1',
                    'al1',
                    TIMESTAMP '2026-01-01 14:00:00',
                    DATE '2026-01-01'
                ),
                (
                    's2',
                    'a1',
                    't2',
                    'al1',
                    TIMESTAMP '2026-01-01 14:00:42',
                    DATE '2026-01-01'
                )
            """
        )

        connection.execute(
            Path("sql/lastfm/034_mart_listening_sessions.sql").read_text(encoding="utf-8")
        )

        result = connection.execute(
            """
            SELECT
                session_span_seconds,
                session_span_minutes,
                scrobble_count

            FROM mart_listening_sessions
            """
        ).fetchone()

    assert result is not None

    span_seconds = result[0]
    span_minutes = result[1]
    scrobble_count = result[2]

    assert span_seconds == 42
    assert abs(span_minutes - span_seconds / 60.0) < 1e-9
    assert scrobble_count == 2


def test_listening_sessions_respect_30_minute_gap(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"

    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE fact_scrobble (
                scrobble_id VARCHAR,
                artist_id VARCHAR,
                track_id VARCHAR,
                album_id VARCHAR,
                scrobbled_at_local TIMESTAMP,
                listening_date DATE
            )
            """
        )

        connection.execute(
            """
            INSERT INTO fact_scrobble
            VALUES
                (
                    's1',
                    'a1',
                    't1',
                    'al1',
                    TIMESTAMP '2026-01-01 12:00:00',
                    DATE '2026-01-01'
                ),
                (
                    's2',
                    'a1',
                    't2',
                    'al1',
                    TIMESTAMP '2026-01-01 12:30:00',
                    DATE '2026-01-01'
                ),
                (
                    's3',
                    'a1',
                    't3',
                    'al1',
                    TIMESTAMP '2026-01-01 13:00:01',
                    DATE '2026-01-01'
                )
            """
        )

        connection.execute(
            Path("sql/lastfm/034_mart_listening_sessions.sql").read_text(encoding="utf-8")
        )

        sessions = connection.execute(
            """
            SELECT
                session_number,
                session_span_seconds,
                scrobble_count

            FROM mart_listening_sessions

            ORDER BY
                session_number
            """
        ).fetchall()

    assert len(sessions) == 2

    first_session = sessions[0]
    second_session = sessions[1]

    assert first_session[1] == 1800
    assert first_session[2] == 2

    assert second_session[1] == 0
    assert second_session[2] == 1


def test_build_analytics_requires_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.duckdb"

    try:
        build_analytics(db_path=db_path)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("build_analytics() should require an existing warehouse.")


def write_album_release_date_cache(
    raw_root: Path,
    *,
    artist: str,
    album: str,
    status: str = "ok",
    first_release_date: str | None = None,
    first_release_year: int | None = None,
) -> str:
    album_id = make_album_id(artist, album)

    cache_dir = raw_root / "enrichment" / "album_release_dates"

    cache_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": status,
        "album_id": album_id,
        "requested_artist": artist,
        "requested_album": album,
        "album_mbid": "11111111-1111-1111-1111-111111111111",
        "scrobble_count": 1,
        "fetched_at_utc": "2026-09-21T12:00:00+00:00",
    }

    if status == "ok":
        payload.update(
            {
                "musicbrainz_entity_type": "release",
                "resolution_method": "release_mbid",
                "release_group_mbid": "22222222-2222-2222-2222-222222222222",
                "first_release_date": first_release_date,
                "first_release_year": first_release_year,
                "matched_title": album,
                "matched_primary_type": "Album",
                "match_score": None,
            }
        )

    elif status == "not_found":
        payload.update({"error_code": None, "error_message": None})

    (cache_dir / f"{album_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    return album_id


def test_build_warehouse_loads_album_release_date_cache(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"

    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at=("2026-09-21T12:00:00+00:00"),
        tracks=[
            historical_track(
                artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_757_930_100
            ),
        ],
    )

    album_a_id = write_album_release_date_cache(
        raw_root,
        artist="Artist A",
        album="Album A",
        status="ok",
        first_release_date="1997-08-12",
        first_release_year=1997,
    )

    album_b_id = write_album_release_date_cache(
        raw_root, artist="Artist B", album="Album B", status="not_found"
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

    with duckdb.connect(str(db_path)) as connection:
        enrichment = connection.execute(
            """
                SELECT
                    album_id,
                    status

                FROM
                    album_release_date_enrichment

                ORDER BY
                    album_id
                """
        ).fetchall()

        release_dates = connection.execute(
            """
                SELECT
                    album_id,
                    first_release_date,
                    first_release_year,
                    resolution_method,
                    matched_primary_type

                FROM
                    bronze_album_release_dates
                """
        ).fetchall()

    assert enrichment == sorted([(album_a_id, "ok"), (album_b_id, "not_found")])

    assert release_dates == [(album_a_id, "1997-08-12", 1997, "release_mbid", "Album")]


def test_album_release_year_bridge_resolves_sources(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at="2026-09-21T12:00:00+00:00",
        tracks=[
            historical_track(
                artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_757_930_100
            ),
            historical_track(
                artist="Artist C", track="Track C", album="Album C", uts=1_757_930_200
            ),
            historical_track(
                artist="Artist D", track="Track D", album="Album D", uts=1_757_930_300
            ),
        ],
    )

    album_a_id = write_album_tag_cache(
        raw_root, artist="Artist A", album="Album A", tags=[("1998", 100)]
    )

    write_album_release_date_cache(
        raw_root,
        artist="Artist A",
        album="Album A",
        first_release_date="1997-08-12",
        first_release_year=1997,
    )

    album_b_id = write_album_tag_cache(
        raw_root, artist="Artist B", album="Album B", tags=[("2004", 100)]
    )

    album_c_id = write_album_tag_cache(
        raw_root, artist="Artist C", album="Album C", tags=[("1971", 100), ("1972", 50)]
    )

    album_d_id = make_album_id("Artist D", "Album D")

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

    with duckdb.connect(str(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                album_id,
                release_year,
                release_decade,
                release_year_source,
                lastfm_candidate_year_count,
                exact_year_match,
                same_decade,
                release_decade_conflict

            FROM bridge_album_release_year

            ORDER BY album_id
            """
        ).fetchall()

    assert rows == sorted(
        [
            (album_a_id, 1997, 1990, "musicbrainz", 1, False, True, False),
            (album_b_id, 2004, 2000, "lastfm_year_tag", 1, None, None, None),
            (album_c_id, None, None, "unknown", 2, None, None, None),
            (album_d_id, None, None, "unknown", 0, None, None, None),
        ]
    )


def test_listening_by_decade_preserves_release_coverage(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at="2026-09-21T12:00:00+00:00",
        tracks=[
            historical_track(
                artist="Artist A", track="Track A", album="Album A", uts=1_757_930_000
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_757_930_100
            ),
            historical_track(
                artist="Artist C", track="Track C", album="Album C", uts=1_757_930_200
            ),
            historical_track(artist="Artist D", track="Track D", album="", uts=1_757_930_300),
        ],
    )

    write_album_release_date_cache(
        raw_root,
        artist="Artist A",
        album="Album A",
        first_release_date="1997-08-12",
        first_release_year=1997,
    )

    write_album_tag_cache(raw_root, artist="Artist B", album="Album B", tags=[("2004", 100)])

    write_album_tag_cache(
        raw_root, artist="Artist C", album="Album C", tags=[("1971", 100), ("1972", 50)]
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

    with duckdb.connect(str(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                release_decade,
                scrobble_count,
                distinct_tracks,
                distinct_albums,
                distinct_artists,
                total_scrobbles,
                scrobbles_with_album,
                release_year_covered_scrobbles,
                release_year_unknown_scrobbles,
                scrobbles_without_album,
                release_year_coverage,
                release_year_dataset_coverage,
                share_of_resolved_scrobbles

            FROM mart_listening_by_decade

            ORDER BY
                release_decade
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0][:10] == (1990, 1, 1, 1, 1, 4, 3, 2, 1, 1)
    assert rows[1][:10] == (2000, 1, 1, 1, 1, 4, 3, 2, 1, 1)
    for row in rows:
        assert abs(row[10] - 2 / 3) < 1e-12
        assert abs(row[11] - 1 / 2) < 1e-12
        assert abs(row[12] - 1 / 2) < 1e-12


def test_listening_by_decade_yearly_normalizes_within_each_year(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    db_path = tmp_path / "test.duckdb"

    write_run(
        raw_root,
        run_id="run-1",
        completed_at="2026-09-21T12:00:00+00:00",
        tracks=[
            historical_track(
                artist="Artist A", track="Track A", album="Album A", uts=1_704_110_400
            ),
            historical_track(
                artist="Artist B", track="Track B", album="Album B", uts=1_704_110_500
            ),
            historical_track(
                artist="Artist C", track="Track C", album="Album C", uts=1_704_110_600
            ),
            historical_track(
                artist="Artist A", track="Track D", album="Album A", uts=1_735_732_800
            ),
            historical_track(artist="Artist D", track="Track E", album="", uts=1_735_732_900),
        ],
    )

    write_album_release_date_cache(
        raw_root,
        artist="Artist A",
        album="Album A",
        first_release_date="1997-08-12",
        first_release_year=1997,
    )

    write_album_tag_cache(raw_root, artist="Artist B", album="Album B", tags=[("2004", 100)])

    write_album_tag_cache(
        raw_root, artist="Artist C", album="Album C", tags=[("1971", 100), ("1972", 50)]
    )

    build_warehouse(raw_root=raw_root, db_path=db_path, sql_root=Path("sql/lastfm"))

    with duckdb.connect(str(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                listening_year,
                release_decade,
                scrobble_count,
                year_total_scrobbles,
                year_scrobbles_with_album,
                year_release_year_covered_scrobbles,
                year_release_year_unknown_scrobbles,
                year_scrobbles_without_album,
                decade_share_within_resolved_year,
                decade_share_within_full_year,
                release_year_coverage,
                release_year_dataset_coverage,
                months_observed,
                is_full_calendar_year

            FROM mart_listening_by_decade_yearly

            ORDER BY
                listening_year,
                release_decade
            """
        ).fetchall()

    assert len(rows) == 3

    row_2024_1990 = rows[0]
    row_2024_2000 = rows[1]
    row_2025_1990 = rows[2]

    assert row_2024_1990[:8] == (2024, 1990, 1, 3, 3, 2, 1, 0)

    assert row_2024_2000[:8] == (2024, 2000, 1, 3, 3, 2, 1, 0)

    for row in (row_2024_1990, row_2024_2000):
        assert abs(row[8] - 1 / 2) < 1e-12
        assert abs(row[9] - 1 / 3) < 1e-12
        assert abs(row[10] - 2 / 3) < 1e-12
        assert abs(row[11] - 2 / 3) < 1e-12
        assert row[12] == 1
        assert row[13] is False

    assert row_2025_1990[:8] == (2025, 1990, 1, 2, 1, 1, 0, 1)
    assert abs(row_2025_1990[8] - 1.0) < 1e-12
    assert abs(row_2025_1990[9] - 1 / 2) < 1e-12
    assert abs(row_2025_1990[10] - 1.0) < 1e-12
    assert abs(row_2025_1990[11] - 1 / 2) < 1e-12
    assert row_2025_1990[12] == 1
    assert row_2025_1990[13] is False
