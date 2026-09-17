import httpx
from lastfm.client import LastFMClient
from lastfm.config import LastFMConfig


def test_recent_tracks_retries_server_error(
    monkeypatch,
):
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            return httpx.Response(
                500,
                request=request,
            )

        return httpx.Response(
            200,
            request=request,
            json={
                "recenttracks": {
                    "track": [],
                    "@attr": {
                        "user": "test-user",
                        "page": "1",
                        "perPage": "200",
                        "totalPages": "0",
                        "total": "0",
                    },
                }
            },
        )

    monkeypatch.setattr(
        "lastfm.client.time.sleep",
        lambda _: None,
    )

    config = LastFMConfig(
        api_key="test-key",
        username="test-user",
    )

    transport = httpx.MockTransport(handler)

    with LastFMClient(
        config,
        max_retries=4,
        transport=transport,
    ) as client:
        payload = client.get_recent_tracks()

    assert attempts == 3

    assert payload["recenttracks"]["@attr"]["user"] == "test-user"


def test_recent_tracks_stops_after_max_retries(
    monkeypatch,
):
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            request=request,
        )

    monkeypatch.setattr(
        "lastfm.client.time.sleep",
        lambda _: None,
    )

    config = LastFMConfig(
        api_key="test-key",
        username="test-user",
    )

    transport = httpx.MockTransport(handler)

    with LastFMClient(
        config,
        max_retries=2,
        transport=transport,
    ) as client:
        try:
            client.get_recent_tracks()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected RuntimeError")

    assert "HTTP 500" in message
    assert "3 attempts" in message

    # Important: secrets must never
    # appear in our own error messages.
    assert "test-key" not in message


def test_album_top_tags_request():
    captured_request = None

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            200,
            request=request,
            json={
                "toptags": {
                    "tag": [
                        {
                            "name": "progressive rock",
                            "count": 100,
                            "url": "https://example.com/tag",
                        }
                    ],
                    "@attr": {
                        "artist": "Rush",
                        "album": "Moving Pictures",
                    },
                }
            },
        )

    config = LastFMConfig(
        api_key="test-key",
        username="test-user",
    )

    transport = httpx.MockTransport(handler)

    with LastFMClient(
        config,
        transport=transport,
    ) as client:
        payload = client.get_album_top_tags(
            artist="Rush",
            album="Moving Pictures",
        )

    assert payload["toptags"]["tag"][0]["name"] == "progressive rock"

    assert captured_request is not None

    params = captured_request.url.params

    assert params["method"] == "album.gettoptags"
    assert params["artist"] == "Rush"
    assert params["album"] == "Moving Pictures"


def test_artist_top_tags_request():
    captured_request = None

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            200,
            request=request,
            json={
                "toptags": {
                    "tag": [
                        {
                            "name": ("progressive rock"),
                            "count": 100,
                            "url": ("https://example.com/tag"),
                        }
                    ],
                    "@attr": {
                        "artist": "Rush",
                    },
                }
            },
        )

    config = LastFMConfig(
        api_key="test-key",
        username="test-user",
    )

    transport = httpx.MockTransport(handler)

    with LastFMClient(
        config,
        transport=transport,
    ) as client:
        payload = client.get_artist_top_tags(
            artist="Rush",
        )

    assert payload["toptags"]["tag"][0]["name"] == "progressive rock"

    assert captured_request is not None

    params = captured_request.url.params

    assert params["method"] == "artist.gettoptags"
    assert params["artist"] == "Rush"
