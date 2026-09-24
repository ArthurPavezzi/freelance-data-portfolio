import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb

from lastfm.client import RETRYABLE_API_ERRORS, LastFMAPIError, LastFMClient
from lastfm.musicbrainz import MusicBrainzClient, MusicBrainzError
from lastfm.warehouse import DEFAULT_DB_PATH

DEFAULT_ENRICHMENT_ROOT = Path("data/raw/lastfm/enrichment/album_tags")

DEFAULT_ARTIST_ENRICHMENT_ROOT = Path("data/raw/lastfm/enrichment/artist_tags")

DEFAULT_RELEASE_DATE_ENRICHMENT_ROOT = Path("data/raw/lastfm/enrichment/album_release_dates")

ReleaseDateCandidateMode = Literal["mbid", "search", "artist_mbid"]


@dataclass(frozen=True, slots=True)
class ArtistCandidate:
    artist_id: str
    artist_name: str
    artist_mbid: str | None
    scrobble_count: int


@dataclass(frozen=True, slots=True)
class AlbumCandidate:
    album_id: str
    artist_name: str
    album_name: str
    album_mbid: str | None
    scrobble_count: int


@dataclass(frozen=True, slots=True)
class AlbumReleaseCandidate:
    album_id: str
    artist_name: str
    artist_mbid: str | None
    album_name: str
    album_mbid: str | None
    scrobble_count: int


def load_album_candidates(
    *, db_path: Path = DEFAULT_DB_PATH, limit: int | None = None
) -> list[AlbumCandidate]:
    query = """
        SELECT
            album.album_id,
            artist.artist_name,
            album.album_name,
            album.album_mbid,
            album.scrobble_count

        FROM dim_album AS album

        JOIN dim_artist AS artist
            ON
                album.artist_id
                = artist.artist_id

        ORDER BY
            album.scrobble_count DESC,
            artist.artist_name,
            album.album_name
    """

    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.execute(query).fetchall()

    candidates = [
        AlbumCandidate(
            album_id=row[0],
            artist_name=row[1],
            album_name=row[2],
            album_mbid=row[3],
            scrobble_count=row[4],
        )
        for row in rows
    ]

    if limit is not None:
        return candidates[:limit]

    return candidates


def load_artist_candidates(
    *, db_path: Path = DEFAULT_DB_PATH, limit: int | None = None
) -> list[ArtistCandidate]:
    query = """
        SELECT
            artist_id,
            artist_name,
            artist_mbid,
            scrobble_count

        FROM dim_artist

        ORDER BY
            scrobble_count DESC,
            artist_name
    """

    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.execute(query).fetchall()

    candidates = [
        ArtistCandidate(
            artist_id=row[0], artist_name=row[1], artist_mbid=row[2], scrobble_count=row[3]
        )
        for row in rows
    ]

    if limit is not None:
        return candidates[:limit]

    return candidates


def artist_cache_path(
    artist_id: str, *, enrichment_root: Path = (DEFAULT_ARTIST_ENRICHMENT_ROOT)
) -> Path:
    return enrichment_root / f"{artist_id}.json"


def _cache_is_final(path: Path) -> bool:
    if not path.exists():
        return False

    record = json.loads(path.read_text(encoding="utf-8"))

    status = record.get("status")

    if status == "ok":
        return True

    if status != "api_error":
        return False

    error_code = int(record.get("error_code", -1))

    return error_code not in RETRYABLE_API_ERRORS


def album_cache_path(album_id: str, *, enrichment_root: Path = (DEFAULT_ENRICHMENT_ROOT)) -> Path:
    return enrichment_root / f"{album_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_album_tags(
    client: LastFMClient,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    enrichment_root: Path = DEFAULT_ENRICHMENT_ROOT,
    limit: int | None = None,
    sleep_seconds: float = 1.0,
    overwrite: bool = False,
) -> dict[str, int]:
    candidates = load_album_candidates(db_path=db_path, limit=limit)

    fetched = 0
    cached = 0
    api_errors = 0

    for position, album in enumerate(candidates, start=1):
        cache_path = album_cache_path(album.album_id, enrichment_root=enrichment_root)

        if cache_path.exists() and not overwrite:
            cached += 1
            continue

        try:
            payload = client.get_album_top_tags(
                artist=(album.artist_name), album=(album.album_name)
            )

            record = {
                "status": "ok",
                "album_id": (album.album_id),
                "requested_artist": (album.artist_name),
                "requested_album": (album.album_name),
                "album_mbid": (album.album_mbid),
                "scrobble_count": (album.scrobble_count),
                "fetched_at_utc": (datetime.now(UTC).isoformat()),
                "response": payload,
            }

            fetched += 1

        except LastFMAPIError as exc:
            record = {
                "status": "api_error",
                "album_id": (album.album_id),
                "requested_artist": (album.artist_name),
                "requested_album": (album.album_name),
                "album_mbid": (album.album_mbid),
                "scrobble_count": (album.scrobble_count),
                "fetched_at_utc": (datetime.now(UTC).isoformat()),
                "error_code": exc.code,
                "error_message": (exc.message),
            }

            api_errors += 1

        _write_json(cache_path, record)

        print(f"[{position}/{len(candidates)}] {album.artist_name} — {album.album_name}")

        if position < len(candidates) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return {
        "candidates": len(candidates),
        "fetched": fetched,
        "cached": cached,
        "api_errors": api_errors,
    }


def enrich_artist_tags(
    client: LastFMClient,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    enrichment_root: Path = DEFAULT_ARTIST_ENRICHMENT_ROOT,
    limit: int | None = None,
    sleep_seconds: float = 1.0,
    overwrite: bool = False,
) -> dict[str, int]:
    candidates = load_artist_candidates(db_path=db_path, limit=limit)

    fetched = 0
    cached = 0
    api_errors = 0

    for position, artist in enumerate(candidates, start=1):
        cache_path = artist_cache_path(artist.artist_id, enrichment_root=(enrichment_root))

        if not overwrite and _cache_is_final(cache_path):
            cached += 1
            continue

        try:
            payload = client.get_artist_top_tags(artist=(artist.artist_name))

            record = {
                "status": "ok",
                "artist_id": (artist.artist_id),
                "requested_artist": (artist.artist_name),
                "artist_mbid": (artist.artist_mbid),
                "scrobble_count": (artist.scrobble_count),
                "fetched_at_utc": (datetime.now(UTC).isoformat()),
                "response": payload,
            }

            fetched += 1

        except LastFMAPIError as exc:
            record = {
                "status": "api_error",
                "artist_id": (artist.artist_id),
                "requested_artist": (artist.artist_name),
                "artist_mbid": (artist.artist_mbid),
                "scrobble_count": (artist.scrobble_count),
                "fetched_at_utc": (datetime.now(UTC).isoformat()),
                "error_code": exc.code,
                "error_message": (exc.message),
            }

            api_errors += 1

        _write_json(cache_path, record)

        print(f"[{position}/{len(candidates)}] {artist.artist_name}")

        if position < len(candidates) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return {
        "candidates": len(candidates),
        "fetched": fetched,
        "cached": cached,
        "api_errors": api_errors,
    }


def load_album_release_candidates(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = None,
    mode: ReleaseDateCandidateMode = "mbid",
) -> list[AlbumReleaseCandidate]:
    if mode == "mbid":
        extra_join = ""
        where_clause = """album.album_mbid IS NOT NULL"""

    elif mode == "search":
        extra_join = """
            INNER JOIN bridge_album_release_year AS release_year
                ON
                    album.album_id
                    = release_year.album_id
        """
        where_clause = """
            album.album_mbid IS NULL
            AND release_year.release_year_source = 'unknown'
            AND release_year.lastfm_candidate_year_count = 0
        """

    elif mode == "artist_mbid":
        extra_join = """
            INNER JOIN bridge_album_release_year AS release_year
                ON
                    album.album_id
                    = release_year.album_id
        """
        where_clause = """
            album.album_mbid IS NULL
            AND release_year.release_year_source = 'unknown'
            AND NULLIF(TRIM(artist.artist_mbid), '') IS NOT NULL
        """

    else:
        raise ValueError(f"Unsupported release-date candidate mode: {mode}")

    query = f"""
        SELECT
            album.album_id,
            artist.artist_name,
            artist.artist_mbid,
            album.album_name,
            album.album_mbid,
            album.scrobble_count

        FROM dim_album AS album

        INNER JOIN dim_artist AS artist
            ON
                album.artist_id
                = artist.artist_id

        {extra_join}

        WHERE
            {where_clause}

        ORDER BY
            album.scrobble_count DESC,
            artist.artist_name,
            album.album_name
    """

    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.execute(query).fetchall()

    candidates = [
        AlbumReleaseCandidate(
            album_id=row[0],
            artist_name=row[1],
            artist_mbid=row[2],
            album_name=row[3],
            album_mbid=row[4],
            scrobble_count=row[5],
        )
        for row in rows
    ]

    if limit is not None:
        return candidates[:limit]

    return candidates


def album_release_date_cache_path(
    album_id: str, *, enrichment_root: Path = DEFAULT_RELEASE_DATE_ENRICHMENT_ROOT
) -> Path:
    return enrichment_root / f"{album_id}.json"


def _release_date_cache_is_final(path: Path, *, mode: ReleaseDateCandidateMode) -> bool:
    if not path.exists():
        return False

    record = json.loads(path.read_text(encoding="utf-8"))
    status = record.get("status")

    # A successful release-date resolution is useful regardless of the
    # candidate mode that produced it.
    if status == "ok":
        return True

    # artist_mbid is intentionally a stronger retry layer for albums that
    # may already have a legacy search-mode not_found/no_release_date cache.
    # Only failures produced by this mode itself should suppress a retry.
    if mode == "artist_mbid" and record.get("candidate_mode") != "artist_mbid":
        return False

    if status in {"not_found", "no_release_date"}:
        return True

    if status != "api_error":
        return False

    return not bool(record.get("retryable", False))


def enrich_album_release_dates(
    client: MusicBrainzClient,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    enrichment_root: Path = DEFAULT_RELEASE_DATE_ENRICHMENT_ROOT,
    limit: int | None = None,
    overwrite: bool = False,
    mode: ReleaseDateCandidateMode = "mbid",
) -> dict[str, int]:
    candidates = load_album_release_candidates(db_path=db_path, limit=limit, mode=mode)

    fetched = 0
    cached = 0
    not_found = 0
    no_release_date = 0
    api_errors = 0

    for position, album in enumerate(candidates, start=1):
        cache_path = album_release_date_cache_path(
            album.album_id, enrichment_root=(enrichment_root)
        )

        if not overwrite and _release_date_cache_is_final(cache_path, mode=mode):
            cached += 1
            continue

        try:
            if mode == "search":
                result = client.search_album_release_date(
                    artist=album.artist_name, album=album.album_name
                )

            elif mode == "artist_mbid":
                if album.artist_mbid is None:
                    raise RuntimeError("artist_mbid candidate is missing artist_mbid.")

                result = client.search_album_release_date_by_artist_mbid(
                    artist=album.artist_name,
                    artist_mbid=album.artist_mbid,
                    album=album.album_name,
                )

            else:
                if album.album_mbid is None:
                    raise RuntimeError("MBID candidate is missing album_mbid.")

                result = client.resolve_album_release_date(
                    album.album_mbid, artist=album.artist_name, album=album.album_name
                )

            if result is None:
                record = {
                    "status": "not_found",
                    "album_id": album.album_id,
                    "requested_artist": album.artist_name,
                    "requested_album": album.album_name,
                    "album_mbid": album.album_mbid,
                    "artist_mbid": album.artist_mbid,
                    "candidate_mode": mode,
                    "scrobble_count": album.scrobble_count,
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                }

                not_found += 1

            elif result.first_release_year is None:
                record = {
                    "status": "no_release_date",
                    "album_id": album.album_id,
                    "requested_artist": album.artist_name,
                    "requested_album": album.album_name,
                    "album_mbid": album.album_mbid,
                    "artist_mbid": album.artist_mbid,
                    "candidate_mode": mode,
                    "musicbrainz_entity_type": result.input_entity_type,
                    "release_group_mbid": result.release_group_mbid or None,
                    "first_release_date": result.first_release_date,
                    "first_release_year": None,
                    "scrobble_count": album.scrobble_count,
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                    "response": result.response,
                    "resolution_method": result.resolution_method,
                    "matched_title": result.matched_title,
                    "matched_primary_type": result.matched_primary_type,
                    "match_score": result.match_score,
                }

                no_release_date += 1

            else:
                record = {
                    "status": "ok",
                    "album_id": album.album_id,
                    "requested_artist": album.artist_name,
                    "requested_album": album.album_name,
                    "album_mbid": album.album_mbid,
                    "artist_mbid": album.artist_mbid,
                    "candidate_mode": mode,
                    "musicbrainz_entity_type": result.input_entity_type,
                    "release_group_mbid": result.release_group_mbid or None,
                    "first_release_date": result.first_release_date,
                    "first_release_year": result.first_release_year,
                    "scrobble_count": album.scrobble_count,
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                    "response": result.response,
                    "resolution_method": result.resolution_method,
                    "matched_title": result.matched_title,
                    "matched_primary_type": result.matched_primary_type,
                    "match_score": result.match_score,
                }

                fetched += 1

        except MusicBrainzError as exc:
            record = {
                "status": "api_error",
                "album_id": album.album_id,
                "requested_artist": album.artist_name,
                "requested_album": album.album_name,
                "album_mbid": album.album_mbid,
                "artist_mbid": album.artist_mbid,
                "candidate_mode": mode,
                "scrobble_count": album.scrobble_count,
                "fetched_at_utc": datetime.now(UTC).isoformat(),
                "error_code": exc.status_code,
                "error_message": str(exc),
                "retryable": exc.retryable,
            }

            api_errors += 1

        _write_json(cache_path, record)

        print(
            f"[{position}/{len(candidates)}] "
            f"{album.artist_name} — {album.album_name} "
            f"[{record['status']}]"
        )

    return {
        "candidates": len(candidates),
        "fetched": fetched,
        "cached": cached,
        "not_found": not_found,
        "no_release_date": no_release_date,
        "api_errors": api_errors,
    }
