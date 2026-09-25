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
        result = client.resolve_album_release_date(
            mbid, artist="Unknown Artist", album="Unknown Album"
        )

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
                301,
                headers={
                    "Location": f"https://musicbrainz.org/ws/2/release-group/{canonical_mbid}"
                },
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
        result = client.resolve_album_release_date(
            old_mbid, artist="Example Artist", album="Example Album"
        )

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
                        "artist-credit": [
                            {"name": "Example Artist", "artist": {"name": "Example Artist"}}
                        ],
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
                        "artist-credit": [
                            {"name": "Vitor Ramil", "artist": {"name": "Vitor Ramil"}}
                        ],
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
                        "artist-credit": [
                            {"name": "Wishbone Ash", "artist": {"name": "Wishbone Ash"}}
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(
            artist="Wishbone Ash", album="Argus (Expanded Edition)"
        )

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
        result = client.search_album_release_date(
            artist="TYR", album="By The Light Of The Northern Star"
        )

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
                        "artist-credit": [
                            {"name": "Foo Fighters", "artist": {"name": "Foo Fighters"}}
                        ],
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
                        "artist-credit": [
                            {"name": "Iron Maiden", "artist": {"name": "Iron Maiden"}}
                        ],
                    },
                    {
                        "id": album_mbid,
                        "title": "A Matter of Life and Death",
                        "primary-type": "Album",
                        "first-release-date": "2006-08-28",
                        "score": 100,
                        "artist-credit": [
                            {"name": "Iron Maiden", "artist": {"name": "Iron Maiden"}}
                        ],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date(
            artist="Iron Maiden", album="A Matter Of Life & Death"
        )

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
        result = client.search_album_release_date(
            artist="Megadeth", album="Countdown To Extinction"
        )

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
                        "artist-credit": [
                            {"name": "Deep Purple", "artist": {"name": "Deep Purple"}}
                        ],
                    },
                    {
                        "id": old_mbid,
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "1972-03-25",
                        "score": 100,
                        "artist-credit": [
                            {"name": "Deep Purple", "artist": {"name": "Deep Purple"}}
                        ],
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
                            "artist-credit": [
                                {"name": "Uriah Heep", "artist": {"name": "Uriah Heep"}}
                            ],
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
                            "artist-credit": [
                                {"name": "Deep Purple", "artist": {"name": "Deep Purple"}}
                            ],
                        },
                        {
                            "id": "77777777-7777-7777-7777-777777777777",
                            "title": "Machine Head",
                            "primary-type": "Album",
                            "first-release-date": "2002",
                            "score": 100,
                            "artist-credit": [
                                {"name": "Deep Purple", "artist": {"name": "Deep Purple"}}
                            ],
                        },
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.resolve_album_release_date(
            input_mbid, artist="Deep Purple", album="Machine Head"
        )

    assert result is None


def test_artist_mbid_search_resolves_concrete_release_to_canonical_group() -> None:
    artist_mbid = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
    release_mbid = "10101010-aaaa-bbbb-cccc-202020202020"
    group_mbid = "11111111-aaaa-bbbb-cccc-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            query = request.url.params["query"]
            assert f"arid:{artist_mbid}" in query
            assert query.startswith('releasegroup:"The Art Of War Re-armed"')
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            params = request.url.params

            if "release-group" in params:
                assert params["release-group"] == group_mbid

                return httpx.Response(
                    200,
                    json={
                        "release-count": 2,
                        "release-offset": 0,
                        "releases": [
                            {
                                "id": "abababab-aaaa-bbbb-cccc-cdcdcdcdcdcd",
                                "title": "The Art of War",
                                "date": "2008-05-30",
                            },
                            {
                                "id": release_mbid,
                                "title": "The Art Of War Re-armed",
                                "date": "2010-01-01",
                            },
                        ],
                    },
                )

            query = params["query"]
            assert f"arid:{artist_mbid}" in query
            assert query.startswith('release:"The Art Of War Re-armed"')
            assert "alias:" not in query

            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": release_mbid,
                            "title": "The Art Of War Re-armed",
                            "score": 100,
                            "release-group": {"id": group_mbid},
                        }
                    ]
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "The Art of War",
                    "primary-type": "Album",
                    "first-release-date": "2008-05-30",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Sabaton",
            artist_mbid=artist_mbid,
            album="The Art Of War Re-armed",
        )

    assert result is not None
    assert result.input_entity_type == "search"
    assert result.input_mbid is None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 2008
    assert result.matched_title == "The Art of War"
    assert result.match_score == 100
    assert result.resolution_method == "release_title_search_artist_mbid"
    assert result.response["date_resolution_method"] == "release_family_first_release"
    assert result.response["musicbrainz_group_first_release_date"] == "2008-05-30"
    assert result.response["release_family_first_release_date"] == "2008-05-30"


def test_artist_mbid_search_uses_canonical_group_year_for_remaster() -> None:
    artist_mbid = "bbbbbbbb-1111-2222-3333-cccccccccccc"
    release_mbid = "21212121-aaaa-bbbb-cccc-313131313131"
    group_mbid = "22222222-aaaa-bbbb-cccc-333333333333"
    release_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            query = request.url.params["query"]
            release_queries.append(query)

            if "2009 Remaster" not in query:
                return httpx.Response(200, json={"releases": []})

            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": release_mbid,
                            "title": "The Man-Machine (2009 Remaster)",
                            "score": 100,
                            "release-group": {"id": group_mbid},
                        }
                    ]
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "The Man-Machine",
                    "primary-type": "Album",
                    "first-release-date": "1978-05",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Kraftwerk",
            artist_mbid=artist_mbid,
            album="The Man-Machine (2009 Remaster)",
        )

    assert result is not None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 1978
    assert result.matched_title == "The Man-Machine"
    assert result.resolution_method == "release_title_search_artist_mbid"
    assert len(release_queries) == 1
    assert "2009 Remaster" in release_queries[0]
    assert result.response["date_resolution_method"] == "release_group_first_release"
    assert result.response["release_family_first_release_date"] is None


def test_artist_mbid_search_uses_first_release_from_matching_title_family() -> None:
    artist_mbid = "bcbcbcbc-1111-2222-3333-cdcdcdcdcdcd"
    release_mbid = "31313131-aaaa-bbbb-cccc-414141414141"
    group_mbid = "32323232-aaaa-bbbb-cccc-424242424242"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            if "release-group" in params:
                assert params["release-group"] == group_mbid

                return httpx.Response(
                    200,
                    json={
                        "release-count": 3,
                        "release-offset": 0,
                        "releases": [
                            {
                                "id": "33333333-aaaa-bbbb-cccc-434343434343",
                                "title": "We Will Rock You (commemorative release)",
                                "date": "1997-12-16",
                            },
                            {
                                "id": "34343434-aaaa-bbbb-cccc-444444444444",
                                "title": "Rock Montreal",
                                "date": "2007-10-29",
                            },
                            {
                                "id": release_mbid,
                                "title": "Queen Rock Montreal",
                                "date": "2020-07-17",
                            },
                        ],
                    },
                )

            query = params["query"]
            assert f"arid:{artist_mbid}" in query
            assert query.startswith('release:"Queen Rock Montreal"')

            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": release_mbid,
                            "title": "Queen Rock Montreal",
                            "score": 100,
                            "release-group": {"id": group_mbid},
                            "date": "2020-07-17",
                        }
                    ]
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "Rock Montreal",
                    "primary-type": "Album",
                    "first-release-date": "1997-12-16",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Queen",
            artist_mbid=artist_mbid,
            album="Queen Rock Montreal",
        )

    assert result is not None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_date == "2007-10-29"
    assert result.first_release_year == 2007
    assert result.matched_title == "Rock Montreal"
    assert result.resolution_method == "release_title_search_artist_mbid"
    assert result.response["date_resolution_method"] == "release_family_first_release"
    assert result.response["musicbrainz_group_first_release_date"] == "1997-12-16"
    assert result.response["release_family_first_release_date"] == "2007-10-29"
    assert result.response["release_family_release_count"] == 2
    assert result.response["release_family_first_release"]["title"] == "Rock Montreal"


def test_artist_mbid_release_search_deduplicates_same_group() -> None:
    artist_mbid = "cccccccc-1111-2222-3333-dddddddddddd"
    group_mbid = "33333333-aaaa-bbbb-cccc-444444444444"
    group_fetches = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal group_fetches

        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": "41414141-aaaa-bbbb-cccc-515151515151",
                            "title": "Example Album",
                            "score": 100,
                            "release-group": {"id": group_mbid},
                        },
                        {
                            "id": "42424242-aaaa-bbbb-cccc-525252525252",
                            "title": "Example Album",
                            "score": 100,
                            "release-group": {"id": group_mbid},
                        },
                    ]
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            group_fetches += 1
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "2001-09-01",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Example Artist",
            artist_mbid=artist_mbid,
            album="Example Album",
        )

    assert result is not None
    assert result.first_release_year == 2001
    assert result.release_group_mbid == group_mbid
    assert group_fetches == 1


def test_artist_mbid_release_search_accepts_same_year_consensus() -> None:
    artist_mbid = "dddddddd-1111-2222-3333-eeeeeeeeeeee"
    ep_group_mbid = "44444444-aaaa-bbbb-cccc-555555555555"
    album_group_mbid = "55555555-aaaa-bbbb-cccc-666666666666"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": "61616161-aaaa-bbbb-cccc-717171717171",
                            "title": "HAARP",
                            "score": 100,
                            "release-group": {"id": ep_group_mbid},
                        },
                        {
                            "id": "62626262-aaaa-bbbb-cccc-727272727272",
                            "title": "HAARP",
                            "score": 100,
                            "release-group": {"id": album_group_mbid},
                        },
                    ]
                },
            )

        if path.endswith(f"/release-group/{ep_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": ep_group_mbid,
                    "title": "HAARP",
                    "primary-type": "EP",
                    "first-release-date": "2008",
                },
            )

        if path.endswith(f"/release-group/{album_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": album_group_mbid,
                    "title": "HAARP",
                    "primary-type": "Album",
                    "first-release-date": "2008-03-17",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Muse",
            artist_mbid=artist_mbid,
            album="H.A.A.R.P.",
        )

    assert result is not None
    assert result.first_release_year == 2008
    assert result.release_group_mbid == album_group_mbid
    assert result.resolution_method == "release_title_search_artist_mbid_consensus"


def test_artist_mbid_search_prefers_exact_release_group_hit_over_weaker_results() -> None:
    artist_mbid = "eeeeeeee-1111-2222-3333-ffffffffffff"
    exact_mbid = "66666666-aaaa-bbbb-cccc-777777777777"
    release_search_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal release_search_called

        path = request.url.path

        if path.rstrip("/").endswith("/release"):
            release_search_called = True
            raise AssertionError("Exact release-group match should resolve before release search")

        query = request.url.params["query"]

        assert query.startswith("releasegroup:")

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
                        "id": "77777777-aaaa-bbbb-cccc-888888888888",
                        "title": "Os Mutantes",
                        "primary-type": "Album",
                        "first-release-date": "1968-06",
                        "score": 91,
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Os Mutantes",
            artist_mbid=artist_mbid,
            album='"Mutantes"',
        )

    assert result is not None
    assert result.release_group_mbid == exact_mbid
    assert result.first_release_year == 1969
    assert result.match_score == 100
    assert result.resolution_method == "release_group_search_artist_mbid"
    assert release_search_called is False


def test_artist_mbid_search_accepts_artist_name_prefix_with_exact_arid() -> None:
    artist_mbid = "ffffffff-1111-2222-3333-aaaaaaaaaaaa"
    group_mbid = "88888888-aaaa-bbbb-cccc-999999999999"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.rstrip("/").endswith("/release"):
            raise AssertionError("Strong ARID release-group title match should resolve directly")

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
            artist="Hermeto Pascoal",
            artist_mbid=artist_mbid,
            album="e sua Visão Original do Forró",
        )

    assert result is not None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 2018
    assert result.resolution_method == "release_group_search_artist_mbid"


def test_artist_mbid_search_does_not_break_release_group_year_conflict() -> None:
    artist_mbid = "12121212-1111-2222-3333-343434343434"
    release_search_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal release_search_called

        path = request.url.path

        if path.rstrip("/").endswith("/release"):
            release_search_called = True
            raise AssertionError(
                "Release search must not break a strong release-group year conflict"
            )

        return httpx.Response(
            200,
            json={
                "release-groups": [
                    {
                        "id": "99999999-aaaa-bbbb-cccc-000000000000",
                        "title": "Machine Head",
                        "primary-type": "Album",
                        "first-release-date": "1972-03-25",
                        "score": 100,
                    },
                    {
                        "id": "00000000-aaaa-bbbb-cccc-111111111111",
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
            artist="Deep Purple",
            artist_mbid=artist_mbid,
            album="Machine Head",
        )

    assert result is None
    assert release_search_called is False


def test_artist_mbid_release_search_rejects_conflicting_group_years() -> None:
    artist_mbid = "23232323-1111-2222-3333-454545454545"
    old_group_mbid = "abababab-aaaa-bbbb-cccc-cdcdcdcdcdcd"
    new_group_mbid = "bcbcbcbc-aaaa-bbbb-cccc-dededededede"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": "73737373-aaaa-bbbb-cccc-838383838383",
                            "title": "Example Album",
                            "score": 100,
                            "release-group": {"id": old_group_mbid},
                        },
                        {
                            "id": "74747474-aaaa-bbbb-cccc-848484848484",
                            "title": "Example Album",
                            "score": 100,
                            "release-group": {"id": new_group_mbid},
                        },
                    ]
                },
            )

        if path.endswith(f"/release-group/{old_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": old_group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "1972",
                },
            )

        if path.endswith(f"/release-group/{new_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": new_group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "2002",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Example Artist",
            artist_mbid=artist_mbid,
            album="Example Album",
        )

    assert result is None


def test_artist_mbid_release_search_rejects_weak_or_wrong_title() -> None:
    artist_mbid = "34343434-1111-2222-3333-565656565656"
    group_fetch_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal group_fetch_called

        path = request.url.path

        if path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        if path.rstrip("/").endswith("/release"):
            return httpx.Response(
                200,
                json={
                    "releases": [
                        {
                            "id": "85858585-aaaa-bbbb-cccc-959595959595",
                            "title": "Example Album",
                            "score": 99,
                            "release-group": {"id": "cdcdcdcd-aaaa-bbbb-cccc-efefefefefef"},
                        },
                        {
                            "id": "86868686-aaaa-bbbb-cccc-969696969696",
                            "title": "Different Album",
                            "score": 100,
                            "release-group": {"id": "dededede-aaaa-bbbb-cccc-f0f0f0f0f0f0"},
                        },
                    ]
                },
            )

        if "/release-group/" in path:
            group_fetch_called = True
            raise AssertionError("Rejected releases must not trigger release-group fetches")

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Example Artist",
            artist_mbid=artist_mbid,
            album="Example Album",
        )

    assert result is None
    assert group_fetch_called is False


def test_artist_mbid_search_does_not_use_alias_field() -> None:
    artist_mbid = "45454545-1111-2222-3333-676767676767"
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        queries.append(query)

        assert "alias:" not in query
        assert f"arid:{artist_mbid}" in query

        if request.url.path.rstrip("/").endswith("/release-group"):
            return httpx.Response(200, json={"release-groups": []})

        return httpx.Response(200, json={"releases": []})

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Tim Maia",
            artist_mbid=artist_mbid,
            album="Tim Maia 1971",
        )

    assert result is None
    assert len(queries) == 3
    assert queries[0].startswith('releasegroup:"Tim Maia 1971"')
    assert queries[1].startswith('release:"Tim Maia 1971"')
    assert queries[2].startswith('release:"Tim Maia 1971"')


def test_artist_mbid_release_index_recovers_verified_release_title() -> None:
    artist_mbid = "56565656-1111-2222-3333-787878787878"
    group_mbid = "c1c1c1c1-aaaa-bbbb-cccc-d2d2d2d2d2d2"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            assert query.startswith('release:"The Art Of War Re-armed"')
            assert f"arid:{artist_mbid}" in query

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

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            assert params["release-group"] == group_mbid

            return httpx.Response(
                200,
                json={
                    "release-count": 1,
                    "release-offset": 0,
                    "releases": [
                        {
                            "id": "d3d3d3d3-aaaa-bbbb-cccc-e4e4e4e4e4e4",
                            "title": "The Art of War: Re-Armed",
                        }
                    ],
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "The Art of War",
                    "primary-type": "Album",
                    "first-release-date": "2008-05-30",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Sabaton",
            artist_mbid=artist_mbid,
            album="The Art Of War Re-armed",
        )

    assert result is not None
    assert result.release_group_mbid == group_mbid
    assert result.first_release_year == 2008
    assert result.matched_title == "The Art of War"
    assert result.resolution_method == "release_index_search_artist_mbid"


def test_artist_mbid_release_index_rejects_unverified_group() -> None:
    artist_mbid = "67676767-1111-2222-3333-898989898989"
    wrong_group_mbid = "e5e5e5e5-aaaa-bbbb-cccc-f6f6f6f6f6f6"
    group_fetch_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal group_fetch_called

        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": wrong_group_mbid,
                            "title": "The Man-Machine",
                            "primary-type": "Album",
                            "first-release-date": "1999",
                            "score": 100,
                        }
                    ]
                },
            )

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            return httpx.Response(
                200,
                json={
                    "release-count": 1,
                    "release-offset": 0,
                    "releases": [
                        {
                            "id": "f7f7f7f7-aaaa-bbbb-cccc-080808080808",
                            "title": "The Man-Machine",
                        }
                    ],
                },
            )

        if path.endswith(f"/release-group/{wrong_group_mbid}"):
            group_fetch_called = True
            raise AssertionError("Unverified group must not be fetched")

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Kraftwerk",
            artist_mbid=artist_mbid,
            album="The Man-Machine (2009 Remaster)",
        )

    assert result is None
    assert group_fetch_called is False


def test_artist_mbid_release_index_browse_pages_until_match() -> None:
    artist_mbid = "78787878-1111-2222-3333-909090909090"
    group_mbid = "09090909-aaaa-bbbb-cccc-101010101010"
    browse_offsets = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "World War Live: Battle of the Baltic Sea",
                            "primary-type": "Album",
                            "first-release-date": "2011-08-05",
                            "score": 100,
                        }
                    ]
                },
            )

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            offset = int(params["offset"])
            browse_offsets.append(offset)

            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "release-count": 2,
                        "release-offset": 0,
                        "releases": [
                            {
                                "id": "11111111-aaaa-bbbb-cccc-212121212121",
                                "title": "World War Live",
                            }
                        ],
                    },
                )

            assert offset == 1

            return httpx.Response(
                200,
                json={
                    "release-count": 2,
                    "release-offset": 1,
                    "releases": [
                        {
                            "id": "12121212-aaaa-bbbb-cccc-222222222222",
                            "title": "World War Live: Battle of the Baltic Sea",
                        }
                    ],
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "World War Live: Battle of the Baltic Sea",
                    "primary-type": "Album",
                    "first-release-date": "2011-08-05",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Sabaton",
            artist_mbid=artist_mbid,
            album="World War Live-Battle Of The Baltic Sea",
        )

    assert result is not None
    assert result.first_release_year == 2011
    assert result.release_group_mbid == group_mbid
    assert browse_offsets == [0, 1]


def test_artist_mbid_release_index_rejects_conflicting_validated_years() -> None:
    artist_mbid = "89898989-1111-2222-3333-a0a0a0a0a0a0"
    old_group_mbid = "13131313-aaaa-bbbb-cccc-232323232323"
    new_group_mbid = "14141414-aaaa-bbbb-cccc-242424242424"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": old_group_mbid,
                            "title": "Example Album",
                            "primary-type": "Album",
                            "first-release-date": "1972",
                            "score": 100,
                        },
                        {
                            "id": new_group_mbid,
                            "title": "Example Album",
                            "primary-type": "Album",
                            "first-release-date": "2002",
                            "score": 100,
                        },
                    ]
                },
            )

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            group_mbid = params["release-group"]

            return httpx.Response(
                200,
                json={
                    "release-count": 1,
                    "release-offset": 0,
                    "releases": [
                        {
                            "id": f"release-{group_mbid}",
                            "title": "Example Album",
                        }
                    ],
                },
            )

        if path.endswith(f"/release-group/{old_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": old_group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "1972",
                },
            )

        if path.endswith(f"/release-group/{new_group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": new_group_mbid,
                    "title": "Example Album",
                    "primary-type": "Album",
                    "first-release-date": "2002",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Example Artist",
            artist_mbid=artist_mbid,
            album="Example Album",
        )

    assert result is None


def test_artist_mbid_release_index_normalizes_punctuation_only_differences() -> None:
    artist_mbid = "90909090-1111-2222-3333-b1b1b1b1b1b1"
    group_mbid = "15151515-aaaa-bbbb-cccc-252525252525"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "Apostrophe (')",
                            "primary-type": "Album",
                            "first-release-date": "1974-04-22",
                            "score": 100,
                        }
                    ]
                },
            )

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            return httpx.Response(
                200,
                json={
                    "release-count": 1,
                    "release-offset": 0,
                    "releases": [
                        {
                            "id": "16161616-aaaa-bbbb-cccc-262626262626",
                            "title": "Apostrophe (')",
                        }
                    ],
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "Apostrophe (')",
                    "primary-type": "Album",
                    "first-release-date": "1974-04-22",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Frank Zappa",
            artist_mbid=artist_mbid,
            album="Apostrophe(')",
        )

    assert result is not None
    assert result.first_release_year == 1974
    assert result.release_group_mbid == group_mbid
    assert result.resolution_method == "release_index_search_artist_mbid"


def test_artist_mbid_release_index_uses_first_release_from_matching_title_family() -> None:
    artist_mbid = "a1a1a1a1-1111-2222-3333-b2b2b2b2b2b2"
    group_mbid = "17171717-aaaa-bbbb-cccc-272727272727"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params

        if path.rstrip("/").endswith("/release-group"):
            query = params["query"]

            if query.startswith("releasegroup:"):
                return httpx.Response(200, json={"release-groups": []})

            return httpx.Response(
                200,
                json={
                    "release-groups": [
                        {
                            "id": group_mbid,
                            "title": "Rock Montreal",
                            "primary-type": "Album",
                            "first-release-date": "1997-12-16",
                            "score": 100,
                        }
                    ]
                },
            )

        if path.rstrip("/").endswith("/release") and "query" in params:
            return httpx.Response(200, json={"releases": []})

        if path.rstrip("/").endswith("/release") and "release-group" in params:
            assert params["release-group"] == group_mbid

            return httpx.Response(
                200,
                json={
                    "release-count": 3,
                    "release-offset": 0,
                    "releases": [
                        {
                            "id": "18181818-aaaa-bbbb-cccc-282828282828",
                            "title": "We Will Rock You (commemorative release)",
                            "date": "1997-12-16",
                        },
                        {
                            "id": "19191919-aaaa-bbbb-cccc-292929292929",
                            "title": "Rock Montreal",
                            "date": "2007-10-29",
                        },
                        {
                            "id": "20202020-aaaa-bbbb-cccc-303030303030",
                            "title": "Queen Rock Montreal",
                            "date": "2020-07-17",
                        },
                    ],
                },
            )

        if path.endswith(f"/release-group/{group_mbid}"):
            return httpx.Response(
                200,
                json={
                    "id": group_mbid,
                    "title": "Rock Montreal",
                    "primary-type": "Album",
                    "first-release-date": "1997-12-16",
                },
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)

    with MusicBrainzClient(transport=transport, request_interval_seconds=0) as client:
        result = client.search_album_release_date_by_artist_mbid(
            artist="Queen",
            artist_mbid=artist_mbid,
            album="Queen Rock Montreal",
        )

    assert result is not None
    assert result.first_release_date == "2007-10-29"
    assert result.first_release_year == 2007
    assert result.release_group_mbid == group_mbid
    assert result.resolution_method == "release_index_search_artist_mbid"
    assert result.response["date_resolution_method"] == "release_family_first_release"
    assert result.response["musicbrainz_group_first_release_date"] == "1997-12-16"
    assert result.response["release_family_first_release_date"] == "2007-10-29"
