import json

import duckdb
from lastfm.enrichment import (
    enrich_album_release_dates,
    load_album_release_candidates,
)
from lastfm.musicbrainz import AlbumReleaseDateResult


def _build_release_candidate_db(path) -> None:
    with duckdb.connect(str(path)) as con:
        con.execute(
            """
            CREATE TABLE dim_artist (
                artist_id VARCHAR,
                artist_name VARCHAR,
                artist_mbid VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE dim_album (
                album_id VARCHAR,
                artist_id VARCHAR,
                album_name VARCHAR,
                album_mbid VARCHAR,
                scrobble_count INTEGER
            )
            """
        )
        con.execute(
            """
            CREATE TABLE bridge_album_release_year (
                album_id VARCHAR,
                release_year_source VARCHAR,
                lastfm_candidate_year_count INTEGER
            )
            """
        )

        con.executemany(
            "INSERT INTO dim_artist VALUES (?, ?, ?)",
            [
                ("artist-a", "Artist A", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                ("artist-b", "Artist B", None),
                ("artist-c", "Artist C", "cccccccc-cccc-cccc-cccc-cccccccccccc"),
            ],
        )
        con.executemany(
            "INSERT INTO dim_album VALUES (?, ?, ?, ?, ?)",
            [
                ("album-a", "artist-a", "Unknown Album", None, 100),
                ("album-b", "artist-b", "No Artist MBID", None, 90),
                (
                    "album-c",
                    "artist-c",
                    "Has Album MBID",
                    "dddddddd-dddd-dddd-dddd-dddddddddddd",
                    80,
                ),
                ("album-d", "artist-c", "Already Resolved", None, 70),
            ],
        )
        con.executemany(
            "INSERT INTO bridge_album_release_year VALUES (?, ?, ?)",
            [
                ("album-a", "unknown", 0),
                ("album-b", "unknown", 0),
                ("album-c", "unknown", 0),
                ("album-d", "lastfm_year_tag", 1),
            ],
        )


class _ArtistMbidClient:
    def __init__(self, *, result):
        self.result = result
        self.calls = []

    def search_album_release_date_by_artist_mbid(
        self, *, artist: str, artist_mbid: str, album: str
    ):
        self.calls.append(
            {
                "artist": artist,
                "artist_mbid": artist_mbid,
                "album": album,
            }
        )
        return self.result

    def search_album_release_date(self, *, artist: str, album: str):
        raise AssertionError("search mode should not be used")

    def resolve_album_release_date(self, mbid: str, *, artist: str, album: str):
        raise AssertionError("MBID mode should not be used")


def _resolved_result() -> AlbumReleaseDateResult:
    return AlbumReleaseDateResult(
        input_entity_type="search",
        input_mbid=None,
        resolution_method="release_index_search_artist_mbid",
        release_group_mbid="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        first_release_date="2008-05-30",
        first_release_year=2008,
        matched_title="Unknown Album",
        matched_primary_type="Album",
        match_score=100,
        response={"verified": True},
    )


def test_load_album_release_candidates_artist_mbid_mode(tmp_path) -> None:
    db_path = tmp_path / "lastfm.duckdb"
    _build_release_candidate_db(db_path)

    candidates = load_album_release_candidates(
        db_path=db_path,
        mode="artist_mbid",
    )

    assert len(candidates) == 1

    candidate = candidates[0]

    assert candidate.album_id == "album-a"
    assert candidate.artist_name == "Artist A"
    assert candidate.artist_mbid == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert candidate.album_name == "Unknown Album"
    assert candidate.album_mbid is None
    assert candidate.scrobble_count == 100


def test_artist_mbid_enrichment_writes_provenance(tmp_path) -> None:
    db_path = tmp_path / "lastfm.duckdb"
    enrichment_root = tmp_path / "album_release_dates"
    _build_release_candidate_db(db_path)

    client = _ArtistMbidClient(result=_resolved_result())

    summary = enrich_album_release_dates(
        client,
        db_path=db_path,
        enrichment_root=enrichment_root,
        mode="artist_mbid",
    )

    assert summary == {
        "candidates": 1,
        "fetched": 1,
        "cached": 0,
        "not_found": 0,
        "no_release_date": 0,
        "api_errors": 0,
    }
    assert client.calls == [
        {
            "artist": "Artist A",
            "artist_mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "album": "Unknown Album",
        }
    ]

    record = json.loads((enrichment_root / "album-a.json").read_text(encoding="utf-8"))

    assert record["status"] == "ok"
    assert record["candidate_mode"] == "artist_mbid"
    assert record["artist_mbid"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert record["album_mbid"] is None
    assert record["release_group_mbid"] == "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    assert record["first_release_year"] == 2008
    assert record["resolution_method"] == "release_index_search_artist_mbid"


def test_artist_mbid_enrichment_retries_legacy_not_found_cache(tmp_path) -> None:
    db_path = tmp_path / "lastfm.duckdb"
    enrichment_root = tmp_path / "album_release_dates"
    _build_release_candidate_db(db_path)

    enrichment_root.mkdir(parents=True)
    (enrichment_root / "album-a.json").write_text(
        json.dumps(
            {
                "status": "not_found",
                "album_id": "album-a",
                "requested_artist": "Artist A",
                "requested_album": "Unknown Album",
                "album_mbid": None,
            }
        ),
        encoding="utf-8",
    )

    client = _ArtistMbidClient(result=_resolved_result())

    summary = enrich_album_release_dates(
        client,
        db_path=db_path,
        enrichment_root=enrichment_root,
        mode="artist_mbid",
    )

    assert summary["fetched"] == 1
    assert summary["cached"] == 0
    assert len(client.calls) == 1

    record = json.loads((enrichment_root / "album-a.json").read_text(encoding="utf-8"))

    assert record["status"] == "ok"
    assert record["candidate_mode"] == "artist_mbid"
    assert record["first_release_year"] == 2008


def test_artist_mbid_enrichment_keeps_same_mode_final_cache(tmp_path) -> None:
    db_path = tmp_path / "lastfm.duckdb"
    enrichment_root = tmp_path / "album_release_dates"
    _build_release_candidate_db(db_path)

    enrichment_root.mkdir(parents=True)
    (enrichment_root / "album-a.json").write_text(
        json.dumps(
            {
                "status": "not_found",
                "candidate_mode": "artist_mbid",
                "album_id": "album-a",
                "requested_artist": "Artist A",
                "requested_album": "Unknown Album",
                "album_mbid": None,
                "artist_mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
        ),
        encoding="utf-8",
    )

    client = _ArtistMbidClient(result=_resolved_result())

    summary = enrich_album_release_dates(
        client,
        db_path=db_path,
        enrichment_root=enrichment_root,
        mode="artist_mbid",
    )

    assert summary == {
        "candidates": 1,
        "fetched": 0,
        "cached": 1,
        "not_found": 0,
        "no_release_date": 0,
        "api_errors": 0,
    }
    assert client.calls == []
