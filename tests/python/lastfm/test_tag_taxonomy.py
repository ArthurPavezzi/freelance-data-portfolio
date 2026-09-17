from pathlib import Path

import pytest
from lastfm.tag_taxonomy import (
    CuratedTagClassification,
    build_accent_genre_index,
    build_compact_genre_index,
    compact_genre_key,
    load_genre_aliases,
    resolve_genre,
)


def test_compact_genre_key():
    assert compact_genre_key("Synth-Pop") == "synthpop"

    assert compact_genre_key("Dark Wave") == "darkwave"


def test_exact_genre_resolution():
    genres = {
        "progressive rock",
    }

    result = resolve_genre(
        "Progressive Rock",
        genres=genres,
    )

    assert result.canonical_genre == ("progressive rock")

    assert result.method == ("musicbrainz_exact")


def test_compact_alias_resolution():
    genres = {
        "hip hop",
        "synth-pop",
        "dark wave",
    }

    index = build_compact_genre_index(genres)

    hip_hop = resolve_genre(
        "hip-hop",
        genres=genres,
        compact_index=index,
    )

    synthpop = resolve_genre(
        "synthpop",
        genres=genres,
        compact_index=index,
    )

    darkwave = resolve_genre(
        "darkwave",
        genres=genres,
        compact_index=index,
    )

    assert hip_hop.canonical_genre == "hip hop"

    assert synthpop.canonical_genre == "synth-pop"

    assert darkwave.canonical_genre == "dark wave"

    assert hip_hop.method == ("compact_alias")


def test_compact_alias_rejects_collision():
    genres = {
        "ab-c",
        "a-bc",
    }

    index = build_compact_genre_index(genres)

    result = resolve_genre(
        "abc",
        genres=genres,
        compact_index=index,
    )

    assert result.canonical_genre is None

    assert result.method == ("unresolved")


def test_manual_alias_resolution(
    tmp_path: Path,
):
    alias_path = tmp_path / "aliases.csv"

    alias_path.write_text(
        ("tag_norm,canonical_genre,notes\nrnb,r&b,Common abbreviation\n"),
        encoding="utf-8",
    )

    aliases = load_genre_aliases(alias_path)

    result = resolve_genre(
        "RNB",
        genres={"r&b"},
        aliases=aliases,
    )

    assert result.canonical_genre == ("r&b")

    assert result.method == ("manual_alias")


def test_invalid_manual_alias_target():
    with pytest.raises(
        ValueError,
        match=("Alias target is not a MusicBrainz genre"),
    ):
        resolve_genre(
            "made-up-tag",
            genres={"rock"},
            aliases={"made-up-tag": ("nonexistent genre")},
        )


from lastfm.tag_taxonomy import (
    classify_tag,
    load_tag_classifications,
)


def test_era_tags_are_classified_automatically():
    genres: set[str] = set()

    for tag in (
        "70s",
        "1970s",
        "2019",
    ):
        result = classify_tag(
            tag,
            genres=genres,
        )

        assert result.tag_type == "era"
        assert result.canonical_genre is None
        assert result.method == "era_rule"


def test_curated_non_genre_tag(
    tmp_path: Path,
):
    path = tmp_path / "classification.csv"

    path.write_text(
        ("tag_norm,tag_type,canonical_genre,notes\nbrazilian,geography,,Country descriptor\n"),
        encoding="utf-8",
    )

    curated = load_tag_classifications(path)

    result = classify_tag(
        "Brazilian",
        genres=set(),
        curated=curated,
    )

    assert result.tag_type == "geography"
    assert result.canonical_genre is None


def test_curated_genre_outside_musicbrainz(
    tmp_path: Path,
):
    path = tmp_path / "classification.csv"

    path.write_text(
        ("tag_norm,tag_type,canonical_genre,notes\nrap,genre,rap,Curated genre\n"),
        encoding="utf-8",
    )

    curated = load_tag_classifications(path)

    result = classify_tag(
        "rap",
        genres=set(),
        curated=curated,
    )

    assert result.tag_type == "genre"
    assert result.canonical_genre == "rap"
    assert result.method == "curated"


def test_musicbrainz_genre_precedes_curated_tag():
    result = classify_tag(
        "rock",
        genres={"rock"},
        curated={
            "rock": (
                CuratedTagClassification(
                    tag_type="other",
                    canonical_genre=None,
                )
            )
        },
    )

    assert result.tag_type == "genre"
    assert result.canonical_genre == "rock"
    assert result.method == "musicbrainz_exact"


def test_accent_alias_resolution():
    genres = {
        "forró",
        "tropicália",
        "baião",
    }

    accent_index = build_accent_genre_index(genres)

    cases = {
        "forro": "forró",
        "tropicalia": "tropicália",
        "baiao": "baião",
    }

    for tag, expected in cases.items():
        result = resolve_genre(
            tag,
            genres=genres,
            accent_index=accent_index,
        )

        assert result.canonical_genre == expected
        assert result.method == "accent_alias"


def test_accent_alias_rejects_collision():
    genres = {
        "café",
        "cafe",
    }

    accent_index = build_accent_genre_index(genres)

    result = resolve_genre(
        "cafè",
        genres=genres,
        accent_index=accent_index,
    )

    assert result.canonical_genre is None


def test_classify_tag_accepts_prebuilt_accent_index():
    genres = {"forró"}

    accent_index = build_accent_genre_index(genres)

    result = classify_tag("forro", genres=genres, accent_index=accent_index)

    assert result.canonical_genre == "forró"

    assert result.method == "accent_alias"
