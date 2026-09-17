from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Scrobble:
    artist: str
    track: str
    album: str | None
    artist_mbid: str | None
    track_mbid: str | None
    album_mbid: str | None
    scrobbled_at: datetime | None
    scrobbled_at_uts: int | None
    track_url: str | None
    is_now_playing: bool


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def parse_track(track: dict[str, Any]) -> Scrobble:
    artist = track.get("artist", {})
    album = track.get("album", {})
    date = track.get("date")
    attributes = track.get("@attr", {})

    is_now_playing = attributes.get("nowplaying") == "true"

    if date is None:
        scrobbled_at_uts = None
        scrobbled_at = None
    else:
        scrobbled_at_uts = int(date["uts"])
        scrobbled_at = datetime.fromtimestamp(
            scrobbled_at_uts,
            tz=UTC,
        )

    return Scrobble(
        artist=artist["#text"],
        track=track["name"],
        album=_optional_text(
            album.get("#text"),
        ),
        artist_mbid=_optional_text(
            artist.get("mbid"),
        ),
        track_mbid=_optional_text(
            track.get("mbid"),
        ),
        album_mbid=_optional_text(
            album.get("mbid"),
        ),
        scrobbled_at=scrobbled_at,
        scrobbled_at_uts=scrobbled_at_uts,
        track_url=_optional_text(
            track.get("url"),
        ),
        is_now_playing=is_now_playing,
    )


def parse_recent_tracks(
    payload: dict[str, Any],
) -> list[Scrobble]:
    tracks = payload["recenttracks"]["track"]

    return [parse_track(track) for track in tracks]
