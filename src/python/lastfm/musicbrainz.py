import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Self

import httpx

MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"

MUSICBRAINZ_USER_AGENT = "freelance-data-portfolio/lastfm-analytics-platform"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

REQUEST_INTERVAL_SECONDS = 1.1
MAX_RETRIES = 5

REDIRECT_STATUS_CODES = {301, 302, 307, 308}

MAX_REDIRECTS = 5

_RELEASE_VARIANT_MARKERS = (
    "edition",
    "version",
    "release",
    "expanded",
    "deluxe",
    "bonus",
    "remaster",
    "remastered",
    "remix",
    "anniversary",
    "reissue",
    "live from",
    " anos",
)


class MusicBrainzError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class AlbumReleaseDateResult:
    input_entity_type: str
    input_mbid: str | None
    resolution_method: str
    release_group_mbid: str
    first_release_date: str | None
    first_release_year: int | None
    matched_title: str | None
    matched_primary_type: str | None
    match_score: int | None
    response: dict[str, Any]


class MusicBrainzClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
        max_retries: int = MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.request_interval_seconds = request_interval_seconds

        self.max_retries = max_retries

        self._last_request_at: float | None = None

        self.client = httpx.Client(
            base_url=MUSICBRAINZ_BASE_URL,
            headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return

        elapsed = time.monotonic() - self._last_request_at

        delay = self.request_interval_seconds - elapsed

        if delay > 0:
            time.sleep(delay)

    def _request_json(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        current_url = path
        current_params = params

        retry_attempt = 0
        redirect_count = 0

        while True:
            self._wait_for_rate_limit()

            try:
                response = self.client.get(current_url, params=current_params)
                self._last_request_at = time.monotonic()

            except httpx.RequestError:
                self._last_request_at = time.monotonic()

                if retry_attempt >= self.max_retries:
                    raise MusicBrainzError(
                        f"MusicBrainz request failed after {self.max_retries + 1} attempts",
                        retryable=True,
                    ) from None

                time.sleep(max(2**retry_attempt, 1.0))
                retry_attempt += 1
                continue

            if response.status_code in REDIRECT_STATUS_CODES:
                location = response.headers.get("Location")

                if not location:
                    raise MusicBrainzError(
                        (
                            f"MusicBrainz returned HTTP {response.status_code} without a Location header"
                        ),
                        status_code=response.status_code,
                        retryable=False,
                    )

                redirect_count += 1

                if redirect_count > MAX_REDIRECTS:
                    raise MusicBrainzError(
                        f"MusicBrainz exceeded {MAX_REDIRECTS} redirects",
                        status_code=response.status_code,
                        retryable=False,
                    )

                current_url = location
                current_params = None

                continue

            if response.status_code == 404:
                return None

            if response.status_code in RETRYABLE_STATUS_CODES:
                if retry_attempt >= self.max_retries:
                    raise MusicBrainzError(
                        (
                            "MusicBrainz returned "
                            f"HTTP {response.status_code} "
                            f"after {self.max_retries + 1} attempts"
                        ),
                        status_code=response.status_code,
                        retryable=True,
                    )

                retry_after = response.headers.get("Retry-After")

                try:
                    delay = max(float(retry_after), 1.0)
                except TypeError, ValueError:
                    delay = max(2**retry_attempt, 1.0)

                time.sleep(delay)

                retry_attempt += 1
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MusicBrainzError(
                    f"MusicBrainz returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    retryable=False,
                ) from exc

            return response.json()

    def get_release_group(self, mbid: str) -> dict[str, Any] | None:
        return self._request_json(f"/release-group/{mbid}", params={"fmt": "json"})

    def get_release(self, mbid: str) -> dict[str, Any] | None:
        return self._request_json(
            f"/release/{mbid}", params={"fmt": "json", "inc": "release-groups"}
        )

    def search_album_release_groups(self, *, artist: str, album: str) -> dict[str, Any]:
        query = f"releasegroup:{_quote_lucene(album)} AND artistname:{_quote_lucene(artist)}"

        payload = self._request_json(
            "/release-group/", params={"fmt": "json", "query": query, "limit": "10"}
        )

        if payload is None:
            return {"release-groups": []}

        return payload

    def _search_album_release_groups_by_artist_mbid(
        self, *, artist_mbid: str, album: str
    ) -> dict[str, Any]:
        query = f"releasegroup:{_quote_lucene(album)} AND arid:{artist_mbid}"

        payload = self._request_json(
            "/release-group/", params={"fmt": "json", "query": query, "limit": "10"}
        )

        if payload is None:
            return {"release-groups": []}

        return payload

    def _search_album_releases_by_artist_mbid(
        self, *, artist_mbid: str, album: str
    ) -> dict[str, Any]:
        query = f"release:{_quote_lucene(album)} AND arid:{artist_mbid}"

        payload = self._request_json(
            "/release/",
            params={"fmt": "json", "query": query, "limit": "10"},
        )

        if payload is None:
            return {"releases": []}

        return payload

    def _search_release_groups_by_release_title_artist_mbid(
        self, *, artist_mbid: str, album: str
    ) -> dict[str, Any]:
        query = f"release:{_quote_lucene(album)} AND arid:{artist_mbid}"

        payload = self._request_json(
            "/release-group/",
            params={"fmt": "json", "query": query, "limit": "10"},
        )

        if payload is None:
            return {"release-groups": []}

        return payload

    def _browse_release_group_releases(self, *, release_group_mbid: str) -> list[dict[str, Any]]:
        releases = []
        offset = 0
        limit = 100

        while True:
            payload = self._request_json(
                "/release/",
                params={
                    "fmt": "json",
                    "release-group": release_group_mbid,
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )

            if payload is None:
                break

            page = payload.get("releases", [])

            if not page:
                break

            releases.extend(page)
            offset += len(page)

            release_count = payload.get("release-count")

            if release_count is not None:
                try:
                    total = int(release_count)
                except TypeError, ValueError:
                    total = None

                if total is not None and offset >= total:
                    break

            elif len(page) < limit:
                break

        return releases

    def _release_family_first_date(
        self,
        releases: list[dict[str, Any]],
        *,
        artist: str,
        album: str,
        release_group_title: str,
    ) -> tuple[str | None, dict[str, Any] | None, int]:
        family_releases = []

        for release in releases:
            title = release.get("title") or ""

            matches_requested = (
                _release_evidence_title_match_level(
                    title,
                    artist=artist,
                    album=album,
                )
                > 0
            )
            matches_group = (
                _release_evidence_title_match_level(
                    title,
                    artist=artist,
                    album=release_group_title,
                )
                > 0
            )

            if not (matches_requested or matches_group):
                continue

            release_date = release.get("date") or None

            if _extract_year(release_date) is None:
                continue

            family_releases.append(release)

        if not family_releases:
            return None, None, 0

        earliest_release = min(
            family_releases,
            key=lambda release: _release_date_sort_key(release.get("date") or ""),
        )

        return earliest_release.get("date") or None, earliest_release, len(family_releases)

    def search_album_release_date(
        self, *, artist: str, album: str
    ) -> AlbumReleaseDateResult | None:
        base_title = _strip_release_variant(album)

        search_titles = []

        if _normalize_search_title(base_title) != _normalize_search_title(album):
            # Explicit edition/remaster variants should
            # prefer the underlying canonical title.
            search_titles.append(base_title)

        search_titles.append(album)

        search_attempts = []

        for search_title in search_titles:
            search_payload = self.search_album_release_groups(artist=artist, album=search_title)

            candidates = search_payload.get("release-groups", [])

            candidate_matches = []

            for candidate in candidates:
                if not _artist_credit_matches(candidate, artist=artist):
                    continue

                match_level = _search_title_match_level(
                    candidate.get("title") or "", artist=artist, album=search_title
                )

                if match_level == 0:
                    continue

                candidate_matches.append((match_level, candidate))

            search_attempts.append({"album": search_title, "response": search_payload})

            if not candidate_matches:
                continue

            best_match_level = max(match_level for match_level, _ in candidate_matches)

            strongest_candidates = [
                candidate
                for match_level, candidate in candidate_matches
                if match_level == best_match_level
            ]

            unique_candidates = {
                candidate["id"]: candidate
                for candidate in strongest_candidates
                if candidate.get("id")
            }

            strongest_candidates = list(unique_candidates.values())

            selection = _select_search_candidate(strongest_candidates)

            if selection is None:
                continue

            matched, used_consensus = selection

            first_release_date = matched.get("first-release-date") or None

            is_variant = _normalize_search_title(search_title) != _normalize_search_title(album)

            if is_variant:
                resolution_method = "release_group_search_variant"
            else:
                resolution_method = "release_group_search"

            if used_consensus:
                resolution_method += "_consensus"

            return AlbumReleaseDateResult(
                input_entity_type="search",
                input_mbid=None,
                resolution_method=resolution_method,
                release_group_mbid=matched["id"],
                first_release_date=first_release_date,
                first_release_year=_extract_year(first_release_date),
                matched_title=matched.get("title"),
                matched_primary_type=matched.get("primary-type"),
                match_score=int(matched.get("score", 0)),
                response={
                    "search_attempts": search_attempts,
                    "strongest_candidates": strongest_candidates,
                    "matched_release_group": matched,
                },
            )

        return None

    def search_album_release_date_by_artist_mbid(
        self, *, artist: str, artist_mbid: str, album: str
    ) -> AlbumReleaseDateResult | None:
        base_title = _strip_release_variant(album)

        release_group_titles = []

        if _normalize_search_title(base_title) != _normalize_search_title(album):
            release_group_titles.append(base_title)

        release_group_titles.append(album)

        search_attempts = []

        for search_title in release_group_titles:
            release_group_payload = self._search_album_release_groups_by_artist_mbid(
                artist_mbid=artist_mbid,
                album=search_title,
            )

            release_group_candidates = release_group_payload.get("release-groups", [])
            candidate_matches = []

            for candidate in release_group_candidates:
                match_level = _artist_mbid_search_title_match_level(
                    candidate.get("title") or "",
                    artist=artist,
                    album=search_title,
                )

                if match_level == 0:
                    continue

                candidate_matches.append((match_level, candidate))

            search_attempts.append(
                {
                    "album": search_title,
                    "search_field": "releasegroup",
                    "response": release_group_payload,
                }
            )

            if not candidate_matches:
                continue

            best_match_level = max(match_level for match_level, _ in candidate_matches)

            strongest_candidates = [
                candidate
                for match_level, candidate in candidate_matches
                if match_level == best_match_level
            ]

            unique_candidates = {
                candidate["id"]: candidate
                for candidate in strongest_candidates
                if candidate.get("id")
            }

            strongest_candidates = list(unique_candidates.values())
            selection = _select_search_candidate(strongest_candidates)

            # A strong release-group title match with conflicting
            # years is real ambiguity. Do not let a looser release
            # lookup override it.
            if selection is None:
                return None

            matched, used_consensus = selection
            first_release_date = matched.get("first-release-date") or None
            is_variant = _normalize_search_title(search_title) != _normalize_search_title(album)

            resolution_method = "release_group_search_artist_mbid"

            if is_variant:
                resolution_method += "_variant"

            if used_consensus:
                resolution_method += "_consensus"

            return AlbumReleaseDateResult(
                input_entity_type="search",
                input_mbid=None,
                resolution_method=resolution_method,
                release_group_mbid=matched["id"],
                first_release_date=first_release_date,
                first_release_year=_extract_year(first_release_date),
                matched_title=matched.get("title"),
                matched_primary_type=matched.get("primary-type"),
                match_score=int(matched.get("score", 0)),
                response={
                    "artist_mbid": artist_mbid,
                    "search_attempts": search_attempts,
                    "strongest_candidates": strongest_candidates,
                    "matched_release_group": matched,
                },
            )

        release_titles = [album]

        if _normalize_search_title(base_title) != _normalize_search_title(album):
            # A concrete edition/remaster title is useful evidence at
            # release level, so try it before the stripped base title.
            release_titles.append(base_title)

        for search_title in release_titles:
            release_payload = self._search_album_releases_by_artist_mbid(
                artist_mbid=artist_mbid,
                album=search_title,
            )

            release_candidates = release_payload.get("releases", [])
            release_matches = []

            for candidate in release_candidates:
                if not candidate.get("id"):
                    continue

                if int(candidate.get("score", 0)) != 100:
                    continue

                release_group_info = candidate.get("release-group") or {}

                if not release_group_info.get("id"):
                    continue

                match_level = _artist_mbid_search_title_match_level(
                    candidate.get("title") or "",
                    artist=artist,
                    album=search_title,
                )

                if match_level == 0:
                    continue

                release_matches.append((match_level, candidate))

            search_attempts.append(
                {
                    "album": search_title,
                    "search_field": "release",
                    "response": release_payload,
                }
            )

            if not release_matches:
                continue

            best_match_level = max(match_level for match_level, _ in release_matches)

            strongest_releases = [
                candidate
                for match_level, candidate in release_matches
                if match_level == best_match_level
            ]

            unique_releases = {
                candidate["id"]: candidate
                for candidate in strongest_releases
                if candidate.get("id")
            }

            strongest_releases = list(unique_releases.values())

            release_groups = {}
            matched_release_by_group = {}
            date_resolution_by_group = {}

            for release in strongest_releases:
                release_group_info = release.get("release-group") or {}
                release_group_mbid = release_group_info.get("id")

                if not release_group_mbid or release_group_mbid in release_groups:
                    continue

                release_group = self.get_release_group(release_group_mbid)

                if release_group is None:
                    continue

                release_group_candidate = dict(release_group)
                release_group_candidate["score"] = int(release.get("score", 0))

                group_first_release_date = release_group.get("first-release-date") or None
                release_family_first_date = None
                release_family_first_release = None
                release_family_release_count = 0

                if _release_title_needs_family_date(
                    release.get("title") or "",
                    release_group.get("title") or "",
                ):
                    releases = self._browse_release_group_releases(
                        release_group_mbid=release_group_mbid
                    )
                    (
                        release_family_first_date,
                        release_family_first_release,
                        release_family_release_count,
                    ) = self._release_family_first_date(
                        releases,
                        artist=artist,
                        album=album,
                        release_group_title=release_group.get("title") or "",
                    )

                    if release_family_first_date is not None:
                        release_group_candidate["first-release-date"] = release_family_first_date

                release_groups[release_group_mbid] = release_group_candidate
                matched_release_by_group[release_group_mbid] = release
                date_resolution_by_group[release_group_mbid] = {
                    "date_resolution_method": (
                        "release_family_first_release"
                        if release_family_first_date is not None
                        else "release_group_first_release"
                    ),
                    "musicbrainz_group_first_release_date": group_first_release_date,
                    "release_family_first_release_date": release_family_first_date,
                    "release_family_first_release": release_family_first_release,
                    "release_family_release_count": release_family_release_count,
                }

            strongest_candidates = list(release_groups.values())
            selection = _select_search_candidate(strongest_candidates)

            if selection is None:
                return None

            matched, used_consensus = selection
            matched_release = matched_release_by_group[matched["id"]]
            date_resolution = date_resolution_by_group[matched["id"]]
            first_release_date = matched.get("first-release-date") or None
            is_variant = _normalize_search_title(search_title) != _normalize_search_title(album)

            resolution_method = "release_title_search_artist_mbid"

            if is_variant:
                resolution_method += "_variant"

            if used_consensus:
                resolution_method += "_consensus"

            return AlbumReleaseDateResult(
                input_entity_type="search",
                input_mbid=None,
                resolution_method=resolution_method,
                release_group_mbid=matched["id"],
                first_release_date=first_release_date,
                first_release_year=_extract_year(first_release_date),
                matched_title=matched.get("title"),
                matched_primary_type=matched.get("primary-type"),
                match_score=int(matched_release.get("score", 0)),
                response={
                    "artist_mbid": artist_mbid,
                    "search_attempts": search_attempts,
                    "strongest_releases": strongest_releases,
                    "strongest_candidates": strongest_candidates,
                    "matched_release": matched_release,
                    "matched_release_group": matched,
                    **date_resolution,
                },
            )

        # The release-group search index can find a release title even
        # when the release endpoint search misses it. Use that index only
        # for discovery, then verify the title against the concrete
        # releases that actually belong to each candidate release group.
        discovery_title = album
        discovery_payload = self._search_release_groups_by_release_title_artist_mbid(
            artist_mbid=artist_mbid,
            album=discovery_title,
        )
        discovery_candidates = [
            candidate
            for candidate in discovery_payload.get("release-groups", [])
            if candidate.get("id") and int(candidate.get("score", 0)) == 100
        ]

        search_attempts.append(
            {
                "album": discovery_title,
                "search_field": "release_index",
                "response": discovery_payload,
            }
        )

        validated_matches = []

        for candidate in discovery_candidates:
            release_group_mbid = candidate["id"]
            releases = self._browse_release_group_releases(release_group_mbid=release_group_mbid)

            release_matches = []

            for release in releases:
                match_level = _release_evidence_title_match_level(
                    release.get("title") or "",
                    artist=artist,
                    album=discovery_title,
                )

                if match_level == 0:
                    continue

                release_matches.append((match_level, release))

            if not release_matches:
                continue

            best_match_level = max(match_level for match_level, _ in release_matches)
            strongest_releases = [
                release
                for match_level, release in release_matches
                if match_level == best_match_level
            ]

            release_group = self.get_release_group(release_group_mbid)

            if release_group is None:
                continue

            release_group_candidate = dict(release_group)
            release_group_candidate["score"] = int(candidate.get("score", 0))

            group_first_release_date = release_group.get("first-release-date") or None
            (
                release_family_first_date,
                release_family_first_release,
                release_family_release_count,
            ) = self._release_family_first_date(
                releases,
                artist=artist,
                album=discovery_title,
                release_group_title=release_group.get("title") or "",
            )

            if release_family_first_date is not None:
                release_group_candidate["first-release-date"] = release_family_first_date

            validated_matches.append(
                (
                    best_match_level,
                    release_group_candidate,
                    strongest_releases[0],
                    {
                        "date_resolution_method": (
                            "release_family_first_release"
                            if release_family_first_date is not None
                            else "release_group_first_release"
                        ),
                        "musicbrainz_group_first_release_date": group_first_release_date,
                        "release_family_first_release_date": release_family_first_date,
                        "release_family_first_release": release_family_first_release,
                        "release_family_release_count": release_family_release_count,
                    },
                )
            )

        if not validated_matches:
            return None

        best_validation_level = max(match_level for match_level, _, _, _ in validated_matches)
        strongest_validated = [
            (candidate, release, date_resolution)
            for match_level, candidate, release, date_resolution in validated_matches
            if match_level == best_validation_level
        ]

        unique_candidates = {}
        matched_release_by_group = {}
        date_resolution_by_group = {}

        for candidate, release, date_resolution in strongest_validated:
            release_group_mbid = candidate.get("id")

            if not release_group_mbid or release_group_mbid in unique_candidates:
                continue

            unique_candidates[release_group_mbid] = candidate
            matched_release_by_group[release_group_mbid] = release
            date_resolution_by_group[release_group_mbid] = date_resolution

        strongest_candidates = list(unique_candidates.values())
        selection = _select_search_candidate(strongest_candidates)

        if selection is None:
            return None

        matched, used_consensus = selection
        matched_release = matched_release_by_group[matched["id"]]
        date_resolution = date_resolution_by_group[matched["id"]]
        first_release_date = matched.get("first-release-date") or None
        resolution_method = "release_index_search_artist_mbid"

        if used_consensus:
            resolution_method += "_consensus"

        return AlbumReleaseDateResult(
            input_entity_type="search",
            input_mbid=None,
            resolution_method=resolution_method,
            release_group_mbid=matched["id"],
            first_release_date=first_release_date,
            first_release_year=_extract_year(first_release_date),
            matched_title=matched.get("title"),
            matched_primary_type=matched.get("primary-type"),
            match_score=int(matched.get("score", 0)),
            response={
                "artist_mbid": artist_mbid,
                "search_attempts": search_attempts,
                "validated_release_groups": strongest_candidates,
                "matched_release": matched_release,
                "matched_release_group": matched,
                **date_resolution,
            },
        )

    def resolve_album_release_date(
        self, mbid: str, *, artist: str, album: str
    ) -> AlbumReleaseDateResult | None:
        direct_release_group = self.get_release_group(mbid)

        direct_release = None
        resolved_release_group = None
        input_entity_type = "release-group"

        if direct_release_group is not None:
            if _is_matching_album_group(direct_release_group, album=album):
                first_release_date = direct_release_group.get("first-release-date") or None

                return AlbumReleaseDateResult(
                    input_entity_type="release-group",
                    input_mbid=mbid,
                    resolution_method="direct_mbid",
                    release_group_mbid=direct_release_group["id"],
                    first_release_date=first_release_date,
                    first_release_year=_extract_year(first_release_date),
                    matched_title=direct_release_group.get("title"),
                    matched_primary_type=(direct_release_group.get("primary-type")),
                    match_score=None,
                    response={"direct_release_group": direct_release_group},
                )

        else:
            input_entity_type = "release"
            direct_release = self.get_release(mbid)

            if direct_release is not None:
                release_group_info = direct_release.get("release-group") or {}
                release_group_mbid = release_group_info.get("id")

                if release_group_mbid:
                    resolved_release_group = self.get_release_group(release_group_mbid)

                    if resolved_release_group is not None and _is_matching_album_group(
                        resolved_release_group, album=album
                    ):
                        first_release_date = (
                            resolved_release_group.get("first-release-date") or None
                        )

                        return AlbumReleaseDateResult(
                            input_entity_type="release",
                            input_mbid=mbid,
                            resolution_method="release_mbid",
                            release_group_mbid=release_group_mbid,
                            first_release_date=first_release_date,
                            first_release_year=_extract_year(first_release_date),
                            matched_title=resolved_release_group.get("title"),
                            matched_primary_type=resolved_release_group.get("primary-type"),
                            match_score=None,
                            response={
                                "direct_release": direct_release,
                                "direct_release_group": resolved_release_group,
                            },
                        )

        search_result = self.search_album_release_date(artist=artist, album=album)

        if search_result is None:
            return None

        return AlbumReleaseDateResult(
            input_entity_type=input_entity_type,
            input_mbid=mbid,
            resolution_method=search_result.resolution_method,
            release_group_mbid=search_result.release_group_mbid,
            first_release_date=search_result.first_release_date,
            first_release_year=search_result.first_release_year,
            matched_title=search_result.matched_title,
            matched_primary_type=search_result.matched_primary_type,
            match_score=search_result.match_score,
            response={
                "direct_release": direct_release,
                "direct_release_group": direct_release_group or resolved_release_group,
                "search_fallback": search_result.response,
            },
        )


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None

    year_text = value[:4]

    if len(year_text) != 4 or not year_text.isdigit():
        return None

    return int(year_text)


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_artist_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)

    without_diacritics = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )

    return _normalize_name(without_diacritics)


def _quote_lucene(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')

    return f'"{escaped}"'


def _is_matching_album_group(release_group: dict[str, Any], *, album: str) -> bool:
    primary_type = release_group.get("primary-type") or ""

    title = release_group.get("title") or ""

    return primary_type.casefold() == "album" and _normalize_name(title) == _normalize_name(album)


def _looks_like_release_variant(value: str) -> bool:
    normalized = _normalize_name(value)

    return any(marker in normalized for marker in (_RELEASE_VARIANT_MARKERS))


def _strip_release_variant(value: str) -> str:
    title = value.strip()

    bracket_match = re.search(r"\s*[\(\[]" r"(?P<qualifier>[^()\[\]]+)" r"[\)\]]\s*$", title)

    if bracket_match and _looks_like_release_variant(bracket_match.group("qualifier")):
        return title[: bracket_match.start()].rstrip(" -–—")

    suffix_match = re.search(r"\s+[-–—]\s+" r"(?P<qualifier>.+?)\s*$", title)

    if suffix_match and _looks_like_release_variant(suffix_match.group("qualifier")):
        return title[: suffix_match.start()].strip()

    return title


def _strip_artist_title_prefix(title: str, *, artist: str) -> str:
    normalized_title = _normalize_search_title(title)

    normalized_artist = _normalize_search_title(artist)

    prefix = f"{normalized_artist} - "

    if normalized_title.startswith(prefix):
        return normalized_title[len(prefix) :]

    return normalized_title


def _search_title_match_level(candidate_title: str, *, artist: str, album: str) -> int:
    candidate = _strip_artist_title_prefix(candidate_title, artist=artist)

    requested = _normalize_search_title(album)

    # Strongest match:
    # exact canonical title.
    if candidate == requested:
        return 2

    # Conservative extensions:
    #
    # Ramilonga
    # → Ramilonga: A estética do frio
    #
    # Dead Star
    # → Dead Star / In Your World
    for separator in (": ", " / "):
        if candidate.startswith(f"{requested}{separator}"):
            return 1

    return 0


def _artist_mbid_search_title_match_level(candidate_title: str, *, artist: str, album: str) -> int:
    match_level = _search_title_match_level(candidate_title, artist=artist, album=album)

    if match_level > 0:
        return match_level

    candidate = _normalize_artist_mbid_search_title(candidate_title)
    requested = _normalize_artist_mbid_search_title(album)
    requested_artist = _normalize_artist_mbid_search_title(artist)

    if candidate == requested:
        return 2

    for separator in (": ", " / "):
        if candidate.startswith(f"{requested}{separator}"):
            return 1

    # With an exact artist MBID, accept a release title that simply
    # prefixes the requested album title with the artist name.
    if candidate == f"{requested_artist} {requested}":
        return 2

    return 0


def _normalize_artist_mbid_search_title(value: str) -> str:
    normalized = _normalize_search_title(value)

    # MusicBrainz commonly indexes dotted acronyms without the dots
    # (for example H.A.A.R.P. -> HAARP).
    return normalized.replace(".", "")


def _normalize_release_evidence_title(value: str) -> str:
    normalized = _normalize_artist_mbid_search_title(value)
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)

    return " ".join(normalized.split())


def _release_evidence_title_match_level(candidate_title: str, *, artist: str, album: str) -> int:
    match_level = _artist_mbid_search_title_match_level(
        candidate_title,
        artist=artist,
        album=album,
    )

    if match_level > 0:
        return match_level + 1

    candidate = _normalize_release_evidence_title(candidate_title)
    requested = _normalize_release_evidence_title(album)

    if candidate == requested:
        return 1

    return 0


def _release_title_needs_family_date(release_title: str, release_group_title: str) -> bool:
    stripped_release_title = _strip_release_variant(release_title)

    return _normalize_release_evidence_title(
        stripped_release_title
    ) != _normalize_release_evidence_title(release_group_title)


def _release_date_sort_key(value: str) -> tuple[int, str]:
    year = _extract_year(value)

    if year is None:
        return (9999, value)

    return (year, value)


def _artist_credit_matches(release_group: dict[str, Any], *, artist: str) -> bool:
    requested_artist = _normalize_artist_name(artist)

    artist_names = set()

    for credit in release_group.get("artist-credit") or []:
        if not isinstance(credit, dict):
            continue

        credit_name = credit.get("name")

        if credit_name:
            artist_names.add(_normalize_artist_name(credit_name))

        artist_info = credit.get("artist") or {}

        artist_name = artist_info.get("name")

        if artist_name:
            artist_names.add(_normalize_artist_name(artist_name))

    return requested_artist in artist_names


def _normalize_search_title(value: str) -> str:
    value = value.strip()

    if len(value) >= 2 and (
        (value[0] == value[-1] == '"') or (value[0] == "“" and value[-1] == "”")
    ):
        value = value[1:-1].strip()

    normalized = unicodedata.normalize("NFKD", value)

    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )

    normalized = (
        normalized.casefold()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("‐", "-")
        .replace("-", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("&", " and ")
    )

    return " ".join(normalized.split())


def _select_search_candidate(
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool] | None:
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0], False

    candidates_with_year = [
        (candidate, _extract_year(candidate.get("first-release-date") or None))
        for candidate in candidates
    ]

    known_years = {year for _, year in candidates_with_year if year is not None}

    # Multiple equally strong candidates
    # with conflicting years are genuinely
    # ambiguous.
    if len(known_years) != 1:
        return None

    consensus_year = next(iter(known_years))

    dated_candidates = [
        candidate for candidate, year in candidates_with_year if year == consensus_year
    ]

    primary_type_rank = {"Album": 4, "EP": 3, "Single": 2, "Broadcast": 1, "Other": 0}

    matched = max(
        dated_candidates,
        key=lambda candidate: (
            primary_type_rank.get(candidate.get("primary-type") or "", 0),
            int(candidate.get("score", 0)),
            len(candidate.get("first-release-date") or ""),
        ),
    )

    return matched, True
