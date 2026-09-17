import json
from pathlib import Path
from typing import Any

from lastfm.ingest import (
    ingest_incremental,
    ingest_recent_tracks,
    load_latest_scrobble_uts,
)


class FakeLastFMClient:
    def __init__(
        self,
        pages: dict[
            int,
            dict[str, Any],
        ],
    ) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_recent_tracks(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "page": page,
                "limit": limit,
                "from_timestamp": (from_timestamp),
                "to_timestamp": (to_timestamp),
            }
        )

        return self.pages[page]


def make_payload(
    *,
    page: int,
    total_pages: int,
    total: int,
    tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "recenttracks": {
            "track": tracks,
            "@attr": {
                "user": "test-user",
                "page": str(page),
                "perPage": "200",
                "totalPages": (str(total_pages)),
                "total": str(total),
            },
        }
    }


def historical_track(
    *,
    artist: str,
    track: str,
    uts: int,
) -> dict[str, Any]:
    return {
        "artist": {
            "mbid": "",
            "#text": artist,
        },
        "album": {
            "mbid": "",
            "#text": "",
        },
        "mbid": "",
        "name": track,
        "url": "https://example.com",
        "date": {
            "uts": str(uts),
            "#text": "",
        },
    }


def now_playing_track() -> dict[
    str,
    Any,
]:
    return {
        "artist": {
            "mbid": "",
            "#text": "Artist",
        },
        "album": {
            "mbid": "",
            "#text": "Album",
        },
        "mbid": "",
        "name": "Playing now",
        "url": "https://example.com",
        "@attr": {
            "nowplaying": "true",
        },
    }


def test_ingestion_writes_raw_pages_and_state(
    tmp_path: Path,
):
    pages = {
        1: make_payload(
            page=1,
            total_pages=2,
            total=3,
            tracks=[
                now_playing_track(),
                historical_track(
                    artist="Artist A",
                    track="Track A",
                    uts=300,
                ),
                historical_track(
                    artist="Artist B",
                    track="Track B",
                    uts=200,
                ),
            ],
        ),
        2: make_payload(
            page=2,
            total_pages=2,
            total=3,
            tracks=[
                historical_track(
                    artist="Artist C",
                    track="Track C",
                    uts=100,
                ),
            ],
        ),
    }

    client = FakeLastFMClient(pages)

    result = ingest_recent_tracks(
        client,
        raw_root=tmp_path,
        to_timestamp=500,
        sleep_seconds=0,
    )

    assert result.pages_fetched == 2
    assert result.historical_scrobbles == 3
    assert result.now_playing_observations_skipped == 1

    assert result.earliest_scrobble_uts == 100
    assert result.latest_scrobble_uts == 300

    run_dir = tmp_path / "runs" / result.run_id

    assert (run_dir / "page_00001.json").exists()

    assert (run_dir / "page_00002.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["historical_scrobbles"] == 3

    assert load_latest_scrobble_uts(tmp_path) == 300


def test_incremental_ingestion_uses_overlap(
    tmp_path: Path,
):
    state = {
        "latest_scrobble_uts": 1_000,
        "last_run_id": "previous",
        "updated_at_utc": "test",
    }

    (tmp_path / "state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    pages = {
        1: make_payload(
            page=1,
            total_pages=1,
            total=1,
            tracks=[
                historical_track(
                    artist="Artist",
                    track="Track",
                    uts=1_100,
                )
            ],
        )
    }

    client = FakeLastFMClient(pages)

    ingest_incremental(
        client,
        raw_root=tmp_path,
        overlap_seconds=300,
        sleep_seconds=0,
    )

    assert client.calls[0]["from_timestamp"] == 700

    assert load_latest_scrobble_uts(tmp_path) == 1_100
