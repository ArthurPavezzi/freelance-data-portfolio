from datetime import UTC, datetime

from lastfm.models import parse_recent_tracks, parse_track


def test_parse_historical_scrobble():
    raw = {
        "artist": {
            "mbid": "artist-123",
            "#text": "Iron Maiden",
        },
        "album": {
            "mbid": "album-456",
            "#text": "Powerslave",
        },
        "mbid": "track-789",
        "name": "Flash Of The Blade",
        "url": "https://example.com/track",
        "date": {
            "uts": "1757870000",
            "#text": "14 Sep 2026",
        },
    }

    result = parse_track(raw)

    assert result.artist == "Iron Maiden"
    assert result.track == "Flash Of The Blade"
    assert result.album == "Powerslave"

    assert result.artist_mbid == "artist-123"
    assert result.album_mbid == "album-456"
    assert result.track_mbid == "track-789"

    assert result.scrobbled_at_uts == 1757870000
    assert result.scrobbled_at == datetime.fromtimestamp(
        1757870000,
        tz=UTC,
    )

    assert result.is_now_playing is False


def test_parse_now_playing_track():
    raw = {
        "artist": {
            "mbid": "",
            "#text": "Tool",
        },
        "album": {
            "mbid": "",
            "#text": "Fear Inoculum",
        },
        "mbid": "",
        "name": "Pneuma",
        "url": "https://example.com/track",
        "@attr": {
            "nowplaying": "true",
        },
    }

    result = parse_track(raw)

    assert result.artist == "Tool"
    assert result.track == "Pneuma"

    assert result.artist_mbid is None
    assert result.album_mbid is None
    assert result.track_mbid is None

    assert result.scrobbled_at is None
    assert result.scrobbled_at_uts is None

    assert result.is_now_playing is True


def test_parse_recent_tracks():
    payload = {
        "recenttracks": {
            "track": [
                {
                    "artist": {
                        "mbid": "",
                        "#text": "Artist A",
                    },
                    "album": {
                        "mbid": "",
                        "#text": "Album A",
                    },
                    "mbid": "",
                    "name": "Track A",
                    "url": "https://example.com/a",
                    "date": {
                        "uts": "1757870000",
                        "#text": "",
                    },
                },
                {
                    "artist": {
                        "mbid": "",
                        "#text": "Artist B",
                    },
                    "album": {
                        "mbid": "",
                        "#text": "Album B",
                    },
                    "mbid": "",
                    "name": "Track B",
                    "url": "https://example.com/b",
                    "date": {
                        "uts": "1757870100",
                        "#text": "",
                    },
                },
            ]
        }
    }

    results = parse_recent_tracks(payload)

    assert len(results) == 2
    assert results[0].artist == "Artist A"
    assert results[1].artist == "Artist B"
