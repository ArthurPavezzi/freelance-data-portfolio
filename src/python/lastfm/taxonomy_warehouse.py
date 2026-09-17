from pathlib import Path

import duckdb

from lastfm.genre_vocabulary import (
    load_musicbrainz_genres,
)
from lastfm.tag_taxonomy import (
    build_accent_genre_index,
    build_compact_genre_index,
    classify_tag,
    load_genre_aliases,
    load_tag_classifications,
)

DEFAULT_ALIAS_PATH = Path("data/curated/lastfm/tag_aliases.csv")

DEFAULT_CLASSIFICATION_PATH = Path("data/curated/lastfm/tag_classification.csv")


def _create_tag_taxonomy_table(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE
            dim_tag_taxonomy
        (
            tag_norm VARCHAR PRIMARY KEY,
            tag_type VARCHAR NOT NULL,
            canonical_genre VARCHAR,
            classification_method VARCHAR NOT NULL
        )
        """
    )


def load_tag_taxonomy(
    connection: duckdb.DuckDBPyConnection,
    *,
    raw_root: Path,
    alias_path: Path = DEFAULT_ALIAS_PATH,
    classification_path: Path = DEFAULT_CLASSIFICATION_PATH,
) -> int:
    _create_tag_taxonomy_table(connection)

    genre_path = raw_root / "musicbrainz" / "genres.json"

    if not genre_path.exists():
        return 0

    genres = load_musicbrainz_genres(genre_path)

    aliases = load_genre_aliases(alias_path)

    curated = load_tag_classifications(classification_path)

    compact_index = build_compact_genre_index(genres)

    accent_index = build_accent_genre_index(genres)

    tag_rows = connection.execute(
        """
        SELECT DISTINCT
            tag_norm
        FROM bronze_album_tags

        UNION

        SELECT DISTINCT
            tag_norm
        FROM bronze_artist_tags

        ORDER BY
            tag_norm
        """
    ).fetchall()

    rows = []

    for (tag_norm,) in tag_rows:
        classification = classify_tag(
            tag_norm,
            genres=genres,
            compact_index=compact_index,
            accent_index=accent_index,
            aliases=aliases,
            curated=curated,
        )

        rows.append(
            (
                classification.tag_norm,
                classification.tag_type,
                classification.canonical_genre,
                classification.method,
            )
        )

    if rows:
        connection.executemany(
            """
            INSERT INTO dim_tag_taxonomy
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )

    return len(rows)
