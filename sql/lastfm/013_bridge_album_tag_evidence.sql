CREATE OR REPLACE TABLE bridge_album_tag_evidence AS

WITH album_tagged AS (
    SELECT
        album.album_id,
        album.artist_id,
        tags.tag_rank,
        tags.tag_raw,
        tags.tag_norm,
        tags.tag_weight,
        'album' AS tag_source

    FROM dim_album AS album

    INNER JOIN bronze_album_tags AS tags
        ON album.album_id = tags.album_id
),

artist_fallback AS (
    SELECT
        album.album_id,
        album.artist_id,
        tags.tag_rank,
        tags.tag_raw,
        tags.tag_norm,
        tags.tag_weight,
        'artist_fallback' AS tag_source

    FROM dim_album AS album
    INNER JOIN bronze_artist_tags AS tags
        ON album.artist_id = tags.artist_id

    LEFT JOIN
        album_tag_enrichment
            AS album_enrichment
        ON album.album_id = album_enrichment.album_id

    WHERE COALESCE(album_enrichment.tag_count, 0) = 0
)

SELECT *
FROM album_tagged

UNION ALL

SELECT *
FROM artist_fallback;
