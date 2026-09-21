import httpx
import pytest
from lastfm.musicbrainz import (
    MusicBrainzClient,
    MusicBrainzError,
)


def test_resolve_direct_release_group() -> None:
    release_group_mbid = "11111111-1111-1111-1111-111111111111"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/release-group/{release_group_mbid}")

        return httpx.Response(
            200,
            json={
                "id": release_group_mbid,
                "title": "Example Album",
                "primary-type": "Album",
                "first-release-date": "1998-04-20",
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            release_group_mbid,
            artist="Example Artist",
            album="Example Album",
        )

    assert result is not None
    assert result.input_entity_type == "release-group"
    assert result.resolution_method == "direct_mbid"
    assert result.release_group_mbid == release_group_mbid
    assert result.first_release_date == "1998-04-20"
    assert result.first_release_year == 1998
    assert result.matched_title == "Example Album"
    assert result.matched_primary_type == "Album"
    assert result.match_score is None


def test_resolve_release_to_album_release_group() -> None:
    release_mbid = "22222222-2222-2222-2222-222222222222"

    release_group_mbid = "33333333-3333-3333-3333-333333333333"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{release_mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{release_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": release_mbid,
                    "title": "Example Album",
                    "release-group": {
                        "id": release_group_mbid,
                        "title": "Example Album",
                        "primary-type": "Album",
                    },
                },
            )

        if path.endswith(f"/release-group/{release_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": release_group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "2004-09",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            release_mbid, artist="Example Artist", album="Example Album"
        )

    assert result is not None
    assert result.input_entity_type == "release"
    assert result.resolution_method == "release_mbid"
    assert result.release_group_mbid == release_group_mbid
    assert result.first_release_date == "2004-09"
    assert result.first_release_year == 2004
    assert result.matched_primary_type == "Album"


def test_wrong_release_group_falls_back_to_album_search() -> None:
    release_mbid = "44444444-4444-4444-4444-444444444444"

    wrong_group_mbid = "55555555-5555-5555-5555-555555555555"

    correct_group_mbid = "66666666-6666-6666-6666-666666666666"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{release_mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{release_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": release_mbid,
                    "title": "Lateralus",
                    "release-group": {
                        "id": wrong_group_mbid,
                        "title": "Lateralus",
                        "primary-type": "Single",
                    },
                },
            )

        if path.endswith(f"/release-group/{wrong_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": wrong_group_mbid,
                    "title": "Lateralus",
                    "primary-type": "Single",
                    "first-release-date": "2002-02",
                },
            )

        if path.rstrip("/").endswith("/release-group"):
            assert request.url.params["limit"] == "10"

            query = request.url.params["query"]

            assert "Lateralus" in query
            assert "Tool" in query
            assert "primarytype:album" in query

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": correct_group_mbid,
                            "title": "Lateralus",
                            "primary-type": "Album",
                            "first-release-date": "2001-05-14",
                            "score": 100,
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(release_mbid, artist="Tool", album="Lateralus")

    assert result is not None
    assert result.input_entity_type == "release"
    assert result.resolution_method == "release_group_search"
    assert result.release_group_mbid == correct_group_mbid
    assert result.matched_title == "Lateralus"
    assert result.matched_primary_type == "Album"
    assert result.match_score == 100
    assert result.first_release_year == 2001


def test_unresolved_album_returns_none() -> None:
    mbid = "77777777-7777-7777-7777-777777777777"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{mbid}"):
            return httpx.Response(404)

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            mbid,
            artist="Unknown Artist",
            album="Unknown Album",
        )

    assert result is None


def test_retryable_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(
            503,
            headers={"Retry-After": "1"},
        )

    monkeypatch.setattr(
        "lastfm.musicbrainz.time.sleep",
        lambda _: None,
    )

    transport = httpx.MockTransport(handler)

    with (
        MusicBrainzClient(
            transport=transport,
            request_interval_seconds=0,
            max_retries=1,
        ) as client,
        pytest.raises(MusicBrainzError) as exc_info,
    ):
        client.get_release_group("88888888-8888-8888-8888-888888888888")

    assert calls == 2
    assert exc_info.value.status_code == 503
    assert exc_info.value.retryable is True
