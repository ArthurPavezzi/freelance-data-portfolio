import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lastfm.client import LastFMClient
from lastfm.models import parse_recent_tracks

LOGGER = logging.getLogger(__name__)

DEFAULT_RAW_ROOT = Path("data/raw/lastfm")
DEFAULT_PAGE_SIZE = 200
DEFAULT_OVERLAP_SECONDS = 300


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: str
    pages_fetched: int
    api_total: int
    historical_scrobbles: int
    now_playing_observations_skipped: int
    earliest_scrobble_uts: int | None
    latest_scrobble_uts: int | None
    from_timestamp: int | None
    to_timestamp: int


def _write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _make_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def load_latest_scrobble_uts(
    raw_root: Path = DEFAULT_RAW_ROOT,
) -> int | None:
    state_path = raw_root / "state.json"

    if not state_path.exists():
        return None

    state = json.loads(
        state_path.read_text(
            encoding="utf-8",
        )
    )

    value = state.get("latest_scrobble_uts")

    if value is None:
        return None

    return int(value)


def _write_state(
    raw_root: Path,
    *,
    latest_scrobble_uts: int,
    run_id: str,
) -> None:
    _write_json(
        raw_root / "state.json",
        {
            "latest_scrobble_uts": (latest_scrobble_uts),
            "last_run_id": run_id,
            "updated_at_utc": datetime.now(UTC).isoformat(),
        },
    )


def ingest_recent_tracks(
    client: LastFMClient,
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_seconds: float = 0.5,
) -> IngestionResult:
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200")

    if to_timestamp is None:
        to_timestamp = int(datetime.now(UTC).timestamp())

    run_id = _make_run_id()

    run_dir = raw_root / "runs" / run_id

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    first_payload = client.get_recent_tracks(
        page=1,
        limit=page_size,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )

    attributes = first_payload["recenttracks"]["@attr"]

    api_total = int(attributes["total"])

    total_pages = int(attributes["totalPages"])

    pages_to_fetch = max(
        total_pages,
        1,
    )

    historical_scrobbles = 0
    now_playing_observations_skipped = 0
    timestamps: list[int] = []

    for page in range(
        1,
        pages_to_fetch + 1,
    ):
        if page == 1:
            payload = first_payload
        else:
            payload = client.get_recent_tracks(
                page=page,
                limit=page_size,
                from_timestamp=(from_timestamp),
                to_timestamp=(to_timestamp),
            )

        _write_json(
            run_dir / f"page_{page:05d}.json",
            payload,
        )

        scrobbles = parse_recent_tracks(payload)

        for scrobble in scrobbles:
            if scrobble.is_now_playing:
                now_playing_observations_skipped += 1
                continue

            historical_scrobbles += 1

            if scrobble.scrobbled_at_uts is not None:
                timestamps.append(scrobble.scrobbled_at_uts)

        if page == 1 or page % 25 == 0 or page == pages_to_fetch:
            LOGGER.info(
                "Fetched page %s/%s",
                page,
                pages_to_fetch,
            )

        if page < pages_to_fetch and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    earliest_uts = min(timestamps) if timestamps else None

    latest_uts = max(timestamps) if timestamps else None

    result = IngestionResult(
        run_id=run_id,
        pages_fetched=pages_to_fetch,
        api_total=api_total,
        historical_scrobbles=(historical_scrobbles),
        now_playing_observations_skipped=(now_playing_observations_skipped),
        earliest_scrobble_uts=(earliest_uts),
        latest_scrobble_uts=(latest_uts),
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )

    manifest = asdict(result)

    manifest.update(
        {
            "username": attributes["user"],
            "page_size": page_size,
            "completed_at_utc": (datetime.now(UTC).isoformat()),
        }
    )

    _write_json(
        run_dir / "manifest.json",
        manifest,
    )

    previous_latest = load_latest_scrobble_uts(raw_root)

    state_latest = max(
        value
        for value in (
            previous_latest,
            latest_uts,
        )
        if value is not None
    )

    _write_state(
        raw_root,
        latest_scrobble_uts=(state_latest),
        run_id=run_id,
    )

    return result


def ingest_incremental(
    client: LastFMClient,
    *,
    raw_root: Path = DEFAULT_RAW_ROOT,
    overlap_seconds: int = (DEFAULT_OVERLAP_SECONDS),
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_seconds: float = 0.5,
) -> IngestionResult:
    latest_uts = load_latest_scrobble_uts(raw_root)

    if latest_uts is None:
        from_timestamp = None
    else:
        from_timestamp = max(
            0,
            latest_uts - overlap_seconds,
        )

    return ingest_recent_tracks(
        client,
        raw_root=raw_root,
        from_timestamp=from_timestamp,
        page_size=page_size,
        sleep_seconds=sleep_seconds,
    )
