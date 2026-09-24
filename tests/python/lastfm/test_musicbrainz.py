import httpx
import pytest
from lastfm.musicbrainz import MusicBrainzClient, MusicBrainzError


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
            release_group_mbid, artist="Example Artist", album="Example Album"
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
                    "release-group": {"id": wrong_group_mbid, "title": "Lateralus", "primary-type": "Single"},
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
            assert 'artistname:"Tool"' in query
            assert "primarytype:album" not in query

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
                            "artist-credit": [{"name": "Tool", "artist": {"name": "Tool"}}],
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
        result = client.resolve_album_release_date(mbid, artist="Unknown Artist", album="Unknown Album")

    assert result is None


def test_retryable_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(503, headers={"Retry-After": "1"})

    monkeypatch.setattr("lastfm.musicbrainz.time.sleep", lambda _: None)

    transport = httpx.MockTransport(handler)

    with (
        MusicBrainzClient(transport=transport, request_interval_seconds=0, max_retries=1) as client,
        pytest.raises(MusicBrainzError) as exc_info,
    ):
        client.get_release_group("88888888-8888-8888-8888-888888888888")

    assert calls == 2
    assert exc_info.value.status_code == 503
    assert exc_info.value.retryable is True


def test_missing_primary_type_falls_back_to_album_search() -> None:
    release_mbid = "99999999-9999-9999-9999-999999999999"

    incomplete_group_mbid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    correct_group_mbid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

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
                        "id": incomplete_group_mbid,
                        "title": "Example Album",
                        "primary-type": None,
                    },
                },
            )

        if path.endswith(f"/release-group/{incomplete_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": incomplete_group_mbid,
                    "title": "Example Album",
                    "primary-type": None,
                    "first-release-date": "2005",
                },
            )

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": correct_group_mbid,
                            "title": "Example Album",
                            "primary-type": "Album",
                            "first-release-date": "2004-11-02",
                            "score": 100,
                            "artist-credit": [
                                {"name": "Example Artist", "artist": {"name": "Example Artist"}}
                            ],
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            release_mbid, artist="Example Artist", album="Example Album"
        )

    assert result is not None
    assert result.resolution_method == "release_group_search"
    assert result.release_group_mbid == correct_group_mbid
    assert result.matched_primary_type == "Album"
    assert result.first_release_year == 2004


def test_musicbrainz_redirect_is_followed() -> None:
    old_mbid = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    canonical_mbid = "dddddddd-dddd-dddd-dddd-dddddddddddd"

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)

        if request.url.path.endswith(f"/release-group/{old_mbid}"):
            return httpx.Response(
                301, headers={"Location": f"https://musicbrainz.org/ws/2/release-group/{canonical_mbid}"}
            )

        if request.url.path.endswith(f"/release-group/{canonical_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": canonical_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "1997-08-12",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(old_mbid, artist="Example Artist", album="Example Album")

    assert result is not None
    assert result.release_group_mbid == canonical_mbid
    assert result.first_release_year == 1997
    assert len(calls) == 2


def test_search_album_release_date_without_mbid() -> None:
    release_group_mbid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.rstrip("/").endswith("/release-group")

        query = request.url.params["query"]

        assert "Example Album" in query
        assert "Example Artist" in query
        assert 'artistname:"Example Artist"' in query
        assert "primarytype:album" not in query

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": release_group_mbid,
                        "title": "Example Album",
                        "primary-type": "Album",
                        "first-release-date": "2007-03-12",
                        "score": 100,
                        "artist-credit": [{"name": "Example Artist", "artist": {"name": "Example Artist"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Example Artist", album="Example Album")

    assert result is not None
    assert result.input_entity_type == "search"
    assert result.input_mbid is None
    assert result.resolution_method == "release_group_search"

    assert result.release_group_mbid == release_group_mbid
    assert result.first_release_date == "2007-03-12"
    assert result.first_release_year == 2007
    assert result.match_score == 100


def test_search_album_release_date_rejects_wrong_artist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                        "title": "Example Album",
                        "primary-type": "Album",
                        "first-release-date": "2007-03-12",
                        "score": 100,
                        "artist-credit": [
                            {"name": "Different Artist", "artist": {"name": "Different Artist"}}
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Example Artist", album="Example Album")

    assert result is None


def test_search_album_accepts_exact_artist_title_prefix() -> None:
    group_mbid = "10101010-1010-1010-1010-101010101010"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Cartola - Raizes do Samba",
                        "primary-type": "Album",
                        "first-release-date": "1998",
                        "score": 100,
                        "artist-credit": [{"name": "Cartola", "artist": {"name": "Cartola"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Cartola", album="Raizes Do Samba")

    assert result is not None
    assert result.first_release_year == 1998


def test_search_album_accepts_subtitle_extension() -> None:
    group_mbid = "20202020-2020-2020-2020-202020202020"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Ramilonga: A estética do frio",
                        "primary-type": "Album",
                        "first-release-date": "1997",
                        "score": 100,
                        "artist-credit": [{"name": "Vitor Ramil", "artist": {"name": "Vitor Ramil"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Vitor Ramil", album="Ramilonga")

    assert result is not None
    assert result.first_release_year == 1997


def test_search_album_strips_explicit_edition_suffix() -> None:
    group_mbid = "30303030-3030-3030-3030-303030303030"

    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]

        queries.append(query)

        if "Argus (Expanded Edition)" in query:
            return httpx.Response(200, json={"release-groups": []})

        assert "Argus" in query

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Argus",
                        "primary-type": "Album",
                        "first-release-date": "1972-04-28",
                        "score": 100,
                        "artist-credit": [{"name": "Wishbone Ash", "artist": {"name": "Wishbone Ash"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Wishbone Ash", album="Argus (Expanded Edition)")

    assert result is not None
    assert result.first_release_year == 1972
    assert result.resolution_method == "release_group_search_variant"
    assert len(queries) == 1
    assert "Argus" in queries[0]
    assert "Expanded Edition" not in queries[0]


def test_search_album_does_not_strip_deluxe_from_real_title() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls

        calls += 1
        query = request.url.params["query"]

        assert "Hellbilly Deluxe" in query

        return httpx.Response(200, json={"release-groups": []})

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Rob Zombie", album="Hellbilly Deluxe")

    assert result is None
    assert calls == 1


def test_search_album_matches_artist_ignoring_diacritics() -> None:
    group_mbid = "40404040-4040-4040-4040-404040404040"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "By the Light of the Northern Star",
                        "primary-type": "Album",
                        "first-release-date": "2009-05-29",
                        "score": 100,
                        "artist-credit": [{"name": "Týr", "artist": {"name": "Týr"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="TYR", album="By The Light Of The Northern Star")

    assert result is not None
    assert result.first_release_year == 2009
    assert result.release_group_mbid == group_mbid


def test_search_album_matches_and_ampersand_equivalence() -> None:
    group_mbid = "50505050-5050-5050-5050-505050505050"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Echoes, Silence, Patience & Grace",
                        "primary-type": "Album",
                        "first-release-date": "2007-09-18",
                        "score": 100,
                        "artist-credit": [{"name": "Foo Fighters", "artist": {"name": "Foo Fighters"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(
            artist="Foo Fighters", album="Echoes, Silence, Patience and Grace"
        )

    assert result is not None
    assert result.first_release_year == 2007
    assert result.release_group_mbid == group_mbid


def test_search_album_accepts_same_year_consensus() -> None:
    album_mbid = "60606060-6060-6060-6060-606060606060"
    ep_mbid = "61616161-6161-6161-6161-616161616161"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": ep_mbid,
                        "title": "A Matter of Life and Death",
                        "primary-type": "EP",
                        "first-release-date": "2006",
                        "score": 100,
                        "artist-credit": [{"name": "Iron Maiden", "artist": {"name": "Iron Maiden"}}],
                    },
                    {
                        "id": album_mbid,
                        "title": "A Matter of Life and Death",
                        "primary-type": "Album",
                        "first-release-date": "2006-08-28",
                        "score": 100,
                        "artist-credit": [{"name": "Iron Maiden", "artist": {"name": "Iron Maiden"}}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Iron Maiden", album="A Matter Of Life & Death")

    assert result is not None
    assert result.first_release_year == 2006
    assert result.release_group_mbid == album_mbid
    assert result.resolution_method.endswith("_consensus")


def test_search_album_allows_ep_and_collaborative_artist_credit() -> None:
    group_mbid = "70707070-7070-7070-7070-707070707070"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Collision Course",
                        "primary-type": "EP",
                        "first-release-date": "2004-11-29",
                        "score": 100,
                        "artist-credit": [
                            {"name": "Jay-Z", "artist": {"name": "Jay-Z"}},
                            {"name": "Linkin Park", "artist": {"name": "Linkin Park"}},
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Linkin Park", album="Collision Course")

    assert result is not None
    assert result.first_release_year == 2004
    assert result.matched_primary_type == "EP"


def test_search_album_accepts_slash_title_extension() -> None:
    group_mbid = "80808080-8080-8080-8080-808080808080"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Dead Star / In Your World",
                        "primary-type": "Single",
                        "first-release-date": "2002-06-17",
                        "score": 100,
                        "artist-credit": [{"name": "Muse", "artist": {"name": "Muse"}}],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Muse", album="Dead Star")

    assert result is not None
    assert result.first_release_year == 2002
    assert result.matched_primary_type == "Single"


def test_search_album_prefers_exact_title_over_extension() -> None:
    album_mbid = "90909090-9090-9090-9090-909090909090"
    live_mbid = "91919191-9191-9191-9191-919191919191"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": album_mbid,
                        "title": "Countdown to Extinction",
                        "primary-type": "Album",
                        "first-release-date": "1992-07-06",
                        "score": 100,
                        "artist-credit": [{"name": "Megadeth", "artist": {"name": "Megadeth"}}],
                    },
                    {
                        "id": live_mbid,
                        "title": "Countdown to Extinction: Live",
                        "primary-type": "Album",
                        "first-release-date": "2013-09-24",
                        "score": 93,
                        "artist-credit": [{"name": "Megadeth", "artist": {"name": "Megadeth"}}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Megadeth", album="Countdown To Extinction")

    assert result is not None
    assert result.first_release_year == 1992
    assert result.release_group_mbid == album_mbid


def test_search_album_rejects_conflicting_exact_years() -> None:
    old_mbid = "a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0"
    new_mbid = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": new_mbid,
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "2002",
                        "score": 100,
                        "artist-credit": [{"name": "Deep Purple", "artist": {"name": "Deep Purple"}}],
                    },
                    {
                        "id": old_mbid,
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "1972-03-25",
                        "score": 100,
                        "artist-credit": [{"name": "Deep Purple", "artist": {"name": "Deep Purple"}}],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(artist="Deep Purple", album="Machine Head")

    assert result is None


def test_mbid_resolution_falls_back_to_variant_search() -> None:
    input_mbid = "11111111-1111-1111-1111-111111111111"
    group_mbid = "22222222-2222-2222-2222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{input_mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{input_mbid}"):
            return httpx.Response(404)

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "Demons and Wizards",
                            "primary-type": "Album",
                            "first-release-date": "1972-05-19",
                            "score": 100,
                            "artist-credit": [{"name": "Uriah Heep", "artist": {"name": "Uriah Heep"}}],
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            input_mbid, artist="Uriah Heep", album="Demons and Wizards (Expanded Version)"
        )

    assert result is not None
    assert result.input_mbid == input_mbid
    assert result.first_release_year == 1972
    assert result.release_group_mbid == group_mbid
    assert result.resolution_method == "release_group_search_variant"


def test_mbid_resolution_fallback_allows_ep() -> None:
    input_mbid = "33333333-3333-3333-3333-333333333333"
    group_mbid = "44444444-4444-4444-4444-444444444444"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{input_mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{input_mbid}"):
            return httpx.Response(404)

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "Feedback",
                            "primary-type": "EP",
                            "first-release-date": "2004-06-29",
                            "score": 100,
                            "artist-credit": [{"name": "Rush", "artist": {"name": "Rush"}}],
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(input_mbid, artist="Rush", album="Feedback")

    assert result is not None
    assert result.first_release_year == 2004
    assert result.matched_primary_type == "EP"
    assert result.release_group_mbid == group_mbid


def test_mbid_resolution_fallback_rejects_conflicting_years() -> None:
    input_mbid = "55555555-5555-5555-5555-555555555555"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith(f"/release-group/{input_mbid}"):
            return httpx.Response(404)

        if path.endswith(f"/release/{input_mbid}"):
            return httpx.Response(404)

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": "66666666-6666-6666-6666-666666666666",
                            "title": "Machine Head",
                            "primary-type": "Album",
                            "first-release-date": "1972-03-25",
                            "score": 100,
                            "artist-credit": [{"name": "Deep Purple", "artist": {"name": "Deep Purple"}}],
                        },
                        {
                            "id": "77777777-7777-7777-7777-777777777777",
                            "title": "Machine Head",
                            "primary-type": "Album",
                            "first-release-date": "2002",
                            "score": 100,
                            "artist-credit": [{"name": "Deep Purple", "artist": {"name": "Deep Purple"}}],
                        },
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(input_mbid, artist="Deep Purple", album="Machine Head")

    assert result is None


def test_artist_mbid_search_uses_exact_release_title_fallback() -> None:
    artist_mbid = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
    group_mbid = "11111111-aaaa-bbbb-cccc-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]

        assert f"arid:{artist_mbid}" in query
        assert "alias:" not in query

        if query.startswith("releasegroup:"):
            return httpx.Response(200, json={"release-groups": []})

        assert query.startswith("release:")
        assert "The Art Of War Re-armed" in query

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "The Art of War",
                        "primary-type": "Album",
                        "first-release-date": "2008-05-30",
                        "score": 100,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Sabaton", artist_mbid=artist_mbid, album="The Art Of War Re-armed"
        )

    assert result is not None
    assert result.input_entity_type == "search"
    assert result.input_mbid is None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 2008
    assert result.resolution_method == "release_title_search_artist_mbid"


def test_artist_mbid_search_uses_only_exact_release_hits() -> None:
    artist_mbid = "bbbbbbbb-1111-2222-3333-cccccccccccc"
    ep_mbid = "22222222-aaaa-bbbb-cccc-333333333333"
    album_mbid = "33333333-aaaa-bbbb-cccc-444444444444"

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]

        assert f"arid:{artist_mbid}" in query

        if query.startswith("releasegroup:"):
            return httpx.Response(200, json={"release-groups": []})

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": ep_mbid,
                        "title": "HAARP",
                        "primary-type": "EP",
                        "first-release-date": "2008",
                        "score": 100,
                    },
                    {
                        "id": album_mbid,
                        "title": "HAARP",
                        "primary-type": "Album",
                        "first-release-date": "2008-03-17",
                        "score": 82,
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Muse", artist_mbid=artist_mbid, album="H.A.A.R.P."
        )

    assert result is not None
    assert result.release_group_mbid == ep_mbid
    assert result.first_release_year == 2008
    assert result.match_score == 100
    assert result.resolution_method == "release_title_search_artist_mbid"


def test_artist_mbid_search_prefers_exact_release_hit_over_weaker_results() -> None:
    artist_mbid = "cccccccc-1111-2222-3333-dddddddddddd"
    exact_mbid = "44444444-aaaa-bbbb-cccc-555555555555"

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]

        if query.startswith("releasegroup:"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": exact_mbid,
                            "title": "Mutantes",
                            "primary-type": "Album",
                            "first-release-date": "1969-02",
                            "score": 100,
                        },
                        {
                            "id": "55555555-aaaa-bbbb-cccc-666666666666",
                            "title": "Os Mutantes",
                            "primary-type": "Album",
                            "first-release-date": "1968-06",
                            "score": 91,
                        },
                    ]
                },
            )

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": exact_mbid,
                        "title": "Mutantes",
                        "primary-type": "Album",
                        "first-release-date": "1969-02",
                        "score": 100,
                    },
                    {
                        "id": "66666666-aaaa-bbbb-cccc-777777777777",
                        "title": "Os Mutantes",
                        "primary-type": "Album",
                        "first-release-date": "2014",
                        "score": 86,
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Os Mutantes", artist_mbid=artist_mbid, album='"Mutantes"'
        )

    assert result is not None
    assert result.release_group_mbid == exact_mbid
    assert result.first_release_year == 1969
    assert result.match_score == 100


def test_artist_mbid_search_accepts_release_with_artist_name_prefix() -> None:
    artist_mbid = "dddddddd-1111-2222-3333-eeeeeeeeeeee"
    group_mbid = "77777777-aaaa-bbbb-cccc-888888888888"

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]

        if query.startswith("releasegroup:"):
            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "Hermeto Pascoal e sua Visão Original do Forró",
                            "primary-type": "Album",
                            "first-release-date": "2018-06-01",
                            "score": 100,
                        }
                    ]
                },
            )

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": group_mbid,
                        "title": "Hermeto Pascoal e sua Visão Original do Forró",
                        "primary-type": "Album",
                        "first-release-date": "2018-06-01",
                        "score": 100,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Hermeto Pascoal", artist_mbid=artist_mbid, album="e sua Visão Original do Forró"
        )

    assert result is not None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 2018
    assert result.resolution_method == "release_title_search_artist_mbid"


def test_artist_mbid_search_does_not_break_release_group_year_conflict() -> None:
    artist_mbid = "eeeeeeee-1111-2222-3333-ffffffffffff"
    release_search_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal release_search_called

        query = request.url.params["query"]

        if query.startswith("release:"):
            release_search_called = True
            raise AssertionError("Release-title search must not break a strong release-group year conflict")

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": "88888888-aaaa-bbbb-cccc-999999999999",
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "1972-03-25",
                        "score": 100,
                    },
                    {
                        "id": "99999999-aaaa-bbbb-cccc-000000000000",
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "2002",
                        "score": 100,
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Deep Purple", artist_mbid=artist_mbid, album="Machine Head"
        )

    assert result is None
    assert release_search_called is False


def test_artist_mbid_search_does_not_use_alias_field() -> None:
    artist_mbid = "ffffffff-1111-2222-3333-aaaaaaaaaaaa"
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        queries.append(query)

        assert "alias:" not in query
        assert f"arid:{artist_mbid}" in query

        return httpx.Response(200, json={"release-groups": []})

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Tim Maia", artist_mbid=artist_mbid, album="Tim Maia 1971"
        )

    assert result is None
    assert len(queries) == 2
    assert queries[0].startswith('releasegroup:"Tim Maia 1971"')
    assert queries[1].startswith('release:"Tim Maia 1971"')
