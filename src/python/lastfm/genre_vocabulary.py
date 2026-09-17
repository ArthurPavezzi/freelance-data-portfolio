import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

MUSICBRAINZ_GENRES_URL = "https://musicbrainz.org/ws/2/genre/all"

DEFAULT_GENRE_PATH = Path("data/raw/lastfm/musicbrainz/genres.json")

MUSICBRAINZ_USER_AGENT = "freelance-data-portfolio/lastfm-analytics-platform"

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

PAGE_SIZE = 100
REQUEST_INTERVAL_SECONDS = 1.1
MAX_RETRIES = 5


def normalize_genre(
    value: str,
) -> str:
    return " ".join(value.strip().casefold().split())


def _request_genre_page(
    client: httpx.Client,
    *,
    offset: int,
    limit: int = PAGE_SIZE,
) -> dict[str, Any]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(
                MUSICBRAINZ_GENRES_URL,
                params={
                    "fmt": "json",
                    "limit": limit,
                    "offset": offset,
                },
            )
        except httpx.RequestError:
            if attempt >= MAX_RETRIES:
                raise RuntimeError(
                    "MusicBrainz request failed after "
                    f"{MAX_RETRIES + 1} attempts "
                    f"at offset {offset}"
                ) from None

            time.sleep(2**attempt)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt >= MAX_RETRIES:
                raise RuntimeError(
                    "MusicBrainz returned "
                    f"HTTP {response.status_code} "
                    f"after {MAX_RETRIES + 1} attempts "
                    f"at offset {offset}"
                ) from None

            retry_after = response.headers.get("Retry-After")

            try:
                delay = max(
                    float(retry_after),
                    1.0,
                )
            except (
                TypeError,
                ValueError,
            ):
                delay = max(
                    2**attempt,
                    1.0,
                )

            time.sleep(delay)
            continue

        response.raise_for_status()

        return response.json()

    raise RuntimeError("Unexpected MusicBrainz retry state")


def download_musicbrainz_genres(
    *,
    destination: Path = DEFAULT_GENRE_PATH,
    overwrite: bool = False,
) -> Path:
    if destination.exists() and not overwrite:
        return destination

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    genres: list[dict[str, Any]] = []

    offset = 0
    expected_count: int | None = None

    with httpx.Client(
        headers={
            "User-Agent": (MUSICBRAINZ_USER_AGENT),
        },
        timeout=30.0,
    ) as client:
        while True:
            payload = _request_genre_page(
                client,
                offset=offset,
            )

            page_genres = payload.get(
                "genres",
                [],
            )

            if expected_count is None:
                expected_count = int(payload["genre-count"])

            genres.extend(page_genres)

            print(f"Fetched MusicBrainz genres: {len(genres)}/{expected_count}")

            if len(genres) >= expected_count:
                break

            if not page_genres:
                raise RuntimeError(
                    "MusicBrainz returned an empty page before all genres were fetched"
                )

            offset += len(page_genres)

            time.sleep(REQUEST_INTERVAL_SECONDS)

    if expected_count is None:
        raise RuntimeError("MusicBrainz did not return a genre count")

    if len(genres) != expected_count:
        raise RuntimeError(
            f"MusicBrainz genre count mismatch: expected {expected_count}, received {len(genres)}"
        )

    document = {
        "source": (MUSICBRAINZ_GENRES_URL),
        "fetched_at_utc": (datetime.now(UTC).isoformat()),
        "genre_count": (expected_count),
        "genres": genres,
    }

    destination.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return destination


def load_musicbrainz_genres(
    path: Path = DEFAULT_GENRE_PATH,
) -> set[str]:
    document = json.loads(path.read_text(encoding="utf-8"))

    return {normalize_genre(genre["name"]) for genre in document["genres"] if genre.get("name")}
