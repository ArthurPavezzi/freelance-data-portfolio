import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from lastfm.genre_vocabulary import normalize_genre

DEFAULT_ALIAS_PATH = Path("data/curated/lastfm/tag_aliases.csv")

DEFAULT_CLASSIFICATION_PATH = Path("data/curated/lastfm/tag_classification.csv")


YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")

SHORT_DECADE_PATTERN = re.compile(r"^\d{2}s$")

LONG_DECADE_PATTERN = re.compile(r"^(?:19|20)\d{2}s$")


@dataclass(frozen=True, slots=True)
class GenreResolution:
    tag_norm: str
    canonical_genre: str | None
    method: str

    @property
    def resolved(self) -> bool:
        return self.canonical_genre is not None


@dataclass(frozen=True, slots=True)
class CuratedTagClassification:
    tag_type: str
    canonical_genre: str | None


@dataclass(frozen=True, slots=True)
class TagClassification:
    tag_norm: str
    tag_type: str
    canonical_genre: str | None
    method: str

    @property
    def is_genre(self) -> bool:
        return self.tag_type == "genre" and self.canonical_genre is not None


def accent_fold_genre_key(
    value: str,
) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    return "".join(
        character
        for character in decomposed
        if (not unicodedata.combining(character) and character.isalnum())
    )


def build_accent_genre_index(
    genres: set[str],
) -> dict[str, set[str]]:
    index: defaultdict[
        str,
        set[str],
    ] = defaultdict(set)

    for genre in genres:
        key = accent_fold_genre_key(genre)

        if key:
            index[key].add(genre)

    return dict(index)


def compact_genre_key(
    value: str,
) -> str:
    normalized = normalize_genre(value)

    return "".join(character for character in normalized if character.isalnum())


def build_compact_genre_index(
    genres: set[str],
) -> dict[str, set[str]]:
    index: defaultdict[
        str,
        set[str],
    ] = defaultdict(set)

    for genre in genres:
        key = compact_genre_key(genre)

        if key:
            index[key].add(genre)

    return dict(index)


def load_genre_aliases(
    path: Path = DEFAULT_ALIAS_PATH,
) -> dict[str, str]:
    if not path.exists():
        return {}

    aliases: dict[str, str] = {}

    with path.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            tag_norm = normalize_genre(row["tag_norm"])

            canonical_genre = normalize_genre(row["canonical_genre"])

            if not tag_norm:
                continue

            if not canonical_genre:
                continue

            aliases[tag_norm] = canonical_genre

    return aliases


def load_tag_classifications(
    path: Path = (DEFAULT_CLASSIFICATION_PATH),
) -> dict[
    str,
    CuratedTagClassification,
]:
    if not path.exists():
        return {}

    classifications: dict[
        str,
        CuratedTagClassification,
    ] = {}

    with path.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            tag_norm = normalize_genre(row["tag_norm"])

            tag_type = row["tag_type"].strip().casefold()

            canonical_raw = (
                row.get(
                    "canonical_genre",
                    "",
                )
                or ""
            )

            canonical_genre = normalize_genre(canonical_raw) if canonical_raw.strip() else None

            if not tag_norm:
                continue

            if not tag_type:
                continue

            classifications[tag_norm] = CuratedTagClassification(
                tag_type=tag_type,
                canonical_genre=(canonical_genre),
            )

    return classifications


def resolve_genre(
    tag: str,
    *,
    genres: set[str],
    compact_index: dict[str, set[str]] | None = None,
    accent_index: dict[str, set[str]] | None = None,
    aliases: dict[str, str] | None = None,
) -> GenreResolution:
    tag_norm = normalize_genre(tag)

    if tag_norm in genres:
        return GenreResolution(
            tag_norm=tag_norm,
            canonical_genre=tag_norm,
            method="musicbrainz_exact",
        )

    aliases = aliases or {}

    if tag_norm in aliases:
        canonical_genre = aliases[tag_norm]

        if canonical_genre not in genres:
            raise ValueError(f"Alias target is not a MusicBrainz genre: {canonical_genre}")

        return GenreResolution(
            tag_norm=tag_norm,
            canonical_genre=(canonical_genre),
            method="manual_alias",
        )

    if compact_index is None:
        compact_index = build_compact_genre_index(genres)

    key = compact_genre_key(tag_norm)

    candidates = compact_index.get(key, set())

    if len(candidates) == 1:
        canonical_genre = next(iter(candidates))

        return GenreResolution(
            tag_norm=tag_norm,
            canonical_genre=(canonical_genre),
            method="compact_alias",
        )

    if accent_index is None:
        accent_index = build_accent_genre_index(genres)

    accent_key = accent_fold_genre_key(tag_norm)

    accent_candidates = accent_index.get(accent_key, set())

    if len(accent_candidates) == 1:
        canonical_genre = next(iter(accent_candidates))

        return GenreResolution(
            tag_norm=tag_norm, canonical_genre=(canonical_genre), method="accent_alias"
        )

    return GenreResolution(tag_norm=tag_norm, canonical_genre=None, method="unresolved")


def _is_era_tag(tag_norm: str) -> bool:
    return bool(
        YEAR_PATTERN.fullmatch(tag_norm)
        or SHORT_DECADE_PATTERN.fullmatch(tag_norm)
        or LONG_DECADE_PATTERN.fullmatch(tag_norm)
    )


def classify_tag(
    tag: str,
    *,
    genres: set[str],
    compact_index: dict[str, set[str]] | None = None,
    accent_index: dict[str, set[str]] | None = None,
    aliases: dict[str, str] | None = None,
    curated: dict[str, CuratedTagClassification] | None = None,
) -> TagClassification:
    genre_resolution = resolve_genre(
        tag,
        genres=genres,
        compact_index=compact_index,
        accent_index=accent_index,
        aliases=aliases,
    )

    tag_norm = genre_resolution.tag_norm

    if genre_resolution.resolved:
        return TagClassification(
            tag_norm=tag_norm,
            tag_type="genre",
            canonical_genre=genre_resolution.canonical_genre,
            method=genre_resolution.method,
        )

    curated = curated or {}

    if tag_norm in curated:
        classification = curated[tag_norm]

        return TagClassification(
            tag_norm=tag_norm,
            tag_type=classification.tag_type,
            canonical_genre=classification.canonical_genre,
            method="curated",
        )

    if _is_era_tag(tag_norm):
        return TagClassification(
            tag_norm=tag_norm,
            tag_type="era",
            canonical_genre=None,
            method="era_rule",
        )

    return TagClassification(
        tag_norm=tag_norm,
        tag_type="unknown",
        canonical_genre=None,
        method="unresolved",
    )
