import time
from dataclasses import dataclass
from typing import Any, Self

import httpx

MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"

MUSICBRAINZ_USER_AGENT = "freelance-data-portfolio/lastfm-analytics-platform"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

REQUEST_INTERVAL_SECONDS = 1.1
MAX_RETRIES = 5


class MusicBrainzError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.retryable = retryable


@dataclass(
    frozen=True,
    slots=True,
)
class AlbumReleaseDateResult:
    input_entity_type: str
    input_mbid: str
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
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        for attempt in range(self.max_retries + 1):
            self._wait_for_rate_limit()

            try:
                response = self.client.get(path, params=params)

                self._last_request_at = time.monotonic()

            except httpx.RequestError:
                self._last_request_at = time.monotonic()

                if attempt >= self.max_retries:
                    raise MusicBrainzError(
                        (f"MusicBrainz request failed after {self.max_retries + 1} attempts"),
                        retryable=True,
                    ) from None

                time.sleep(max(2**attempt, 1.0))

                continue

            if response.status_code == 404:
                return None

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt >= self.max_retries:
                    raise MusicBrainzError(
                        (
                            "MusicBrainz returned "
                            f"HTTP {response.status_code} "
                            "after {self.max_retries + 1} attempts"
                        ),
                        status_code=response.status_code,
                        retryable=True,
                    )

                retry_after = response.headers.get("Retry-After")

                try:
                    delay = max(float(retry_after), 1.0)
                except TypeError, ValueError:
                    delay = max(2**attempt, 1.0)

                time.sleep(delay)

                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MusicBrainzError(
                    (f"MusicBrainz returned HTTP {response.status_code}"),
                    status_code=response.status_code,
                    retryable=False,
                ) from exc

            return response.json()

        raise RuntimeError("Unexpected MusicBrainz retry state")

    def get_release_group(self, mbid: str) -> dict[str, Any] | None:
        return self._request_json(f"/release-group/{mbid}", params={"fmt": "json"})

    def get_release(self, mbid: str) -> dict[str, Any] | None:
        return self._request_json(
            f"/release/{mbid}",
            params={"fmt": "json", "inc": "release-groups"},
        )

    def search_album_release_groups(self, *, artist: str, album: str) -> dict[str, Any]:
        query = (
            f"releasegroup:{_quote_lucene(album)} "
            f"AND artist:{_quote_lucene(artist)} "
            "AND primarytype:album"
        )

        payload = self._request_json(
            "/release-group/",
            params={"fmt": "json", "query": query, "limit": "10"},
        )

        if payload is None:
            return {"release-groups": []}

        return payload

    def resolve_album_release_date(
        self,
        mbid: str,
        *,
        artist: str,
        album: str,
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

        search_payload = self.search_album_release_groups(artist=artist, album=album)

        candidates = search_payload.get("release-groups", [])

        matching_candidates = [
            candidate
            for candidate in candidates
            if _is_matching_album_group(candidate, album=album)
        ]

        if not matching_candidates:
            return None

        matching_candidates.sort(key=lambda candidate: int(candidate.get("score", 0)), reverse=True)

        matched = matching_candidates[0]

        first_release_date = matched.get("first-release-date") or None

        return AlbumReleaseDateResult(
            input_entity_type=input_entity_type,
            input_mbid=mbid,
            resolution_method="release_group_search",
            release_group_mbid=(matched["id"]),
            first_release_date=(first_release_date),
            first_release_year=(_extract_year(first_release_date)),
            matched_title=matched.get("title"),
            matched_primary_type=matched.get("primary-type"),
            match_score=int(matched.get("score", 0)),
            response={
                "direct_release": direct_release,
                "direct_release_group": direct_release_group or resolved_release_group,
                "release_group_search": search_payload,
                "matched_release_group": matched,
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


def _quote_lucene(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')

    return f'"{escaped}"'


def _is_matching_album_group(release_group: dict[str, Any], *, album: str) -> bool:
    primary_type = release_group.get("primary-type") or ""

    title = release_group.get("title") or ""

    return primary_type.casefold() == "album" and _normalize_name(title) == _normalize_name(album)
