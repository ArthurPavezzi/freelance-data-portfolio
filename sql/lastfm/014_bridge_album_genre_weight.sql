CREATE OR REPLACE TABLE bridge_album_genre_weight AS

WITH genre_evidence AS (
    SELECT
        evidence.album_id,
        evidence.artist_id,
        evidence.tag_source,
        taxonomy.canonical_genre,
        evidence.tag_norm,
        evidence.tag_weight

    FROM bridge_album_tag_evidence AS evidence

    INNER JOIN dim_tag_taxonomy AS taxonomy
        ON
            evidence.tag_norm
            = taxonomy.tag_norm

    WHERE
        taxonomy.tag_type = 'genre'
        AND taxonomy.canonical_genre IS NOT NULL
        AND evidence.tag_weight > 0
),

canonical_genres AS (
    SELECT
        album_id,
        artist_id,
        tag_source,
        canonical_genre,

        MAX(
            tag_weight
        ) AS genre_weight_raw,

        COUNT(
            DISTINCT tag_norm
        ) AS source_tag_count

    FROM genre_evidence

    GROUP BY
        album_id,
        artist_id,
        tag_source,
        canonical_genre
),

normalized AS (
    SELECT
        album_id,
        artist_id,
        tag_source,
        canonical_genre,
        genre_weight_raw,
        source_tag_count,

        genre_weight_raw::DOUBLE
        / SUM(
            genre_weight_raw
        ) OVER (
            PARTITION BY album_id
        ) AS genre_weight

    FROM canonical_genres
)

SELECT
    album_id,
    artist_id,
    canonical_genre,
    tag_source,
    genre_weight_raw,
    genre_weight,
    source_tag_count,

    ROW_NUMBER() OVER (
        PARTITION BY album_id
        ORDER BY
            genre_weight DESC,
            canonical_genre ASC
    ) AS genre_rank

FROM normalized;
