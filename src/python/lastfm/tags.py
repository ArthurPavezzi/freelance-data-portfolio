from dataclasses import dataclass
from typing import Any


@dataclass(
    frozen=True,
    slots=True,
)
class ArtistTag:
    artist_id: str
    tag_raw: str
    tag_norm: str
    weight: int
    rank: int


def parse_artist_tags(
    artist_id: str,
    payload: dict[str, Any],
) -> list[ArtistTag]:
    raw_tags = payload.get("toptags", {}).get("tag", [])

    if isinstance(
        raw_tags,
        dict,
    ):
        raw_tags = [raw_tags]

    return [
        ArtistTag(
            artist_id=artist_id,
            tag_raw=str(
                tag.get(
                    "name",
                    "",
                )
            ).strip(),
            tag_norm=normalize_tag(str(tag.get("name", ""))),
            weight=int(
                tag.get(
                    "count",
                    0,
                )
                or 0
            ),
            rank=rank,
        )
        for rank, tag in enumerate(
            raw_tags,
            start=1,
        )
        if str(
            tag.get(
                "name",
                "",
            )
        ).strip()
    ]


@dataclass(frozen=True, slots=True)
class AlbumTag:
    album_id: str
    tag_raw: str
    tag_norm: str
    weight: int
    rank: int


def normalize_tag(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def parse_album_tags(
    album_id: str,
    payload: dict[str, Any],
) -> list[AlbumTag]:
    tags = payload.get("toptags", {}).get("tag", [])

    return [
        AlbumTag(
            album_id=album_id,
            tag_raw=tag["name"],
            tag_norm=normalize_tag(tag["name"]),
            weight=int(tag.get("count", 0)),
            rank=rank,
        )
        for rank, tag in enumerate(
            tags,
            start=1,
        )
    ]
