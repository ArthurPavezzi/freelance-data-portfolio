CREATE OR REPLACE TABLE stg_scrobbles AS

WITH normalized AS (
    SELECT
        observation_id,
        run_id,
        source_page,
        source_position,

        TRIM(artist) AS artist,
        TRIM(track) AS track,
        NULLIF(TRIM(album), '') AS album,

        LOWER(TRIM(artist)) AS artist_norm,
        LOWER(TRIM(track)) AS track_norm,
        LOWER(NULLIF(TRIM(album), '')) AS album_norm,

        NULLIF(TRIM(artist_mbid), '') AS artist_mbid,
        NULLIF(TRIM(track_mbid), '') AS track_mbid,
        NULLIF(TRIM(album_mbid), '') AS album_mbid,

        scrobbled_at,
        scrobbled_at_uts,
        track_url,
        ingested_at,
        source_file

    FROM bronze_scrobbles

    WHERE
        NOT is_now_playing
        AND scrobbled_at_uts IS NOT NULL
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY
                scrobbled_at_uts,
                artist_norm,
                track_norm,
                COALESCE(album_norm, '')

            ORDER BY
                ingested_at,
                run_id,
                source_page,
                source_position
        ) AS duplicate_rank
    FROM normalized
)

SELECT
    MD5(
        CONCAT_WS(
            '|',
            CAST(scrobbled_at_uts AS VARCHAR),
            artist_norm,
            track_norm,
            COALESCE(album_norm, '')
        )
    ) AS scrobble_id,

    artist,
    track,
    album,

    artist_norm,
    track_norm,
    album_norm,

    artist_mbid,
    track_mbid,
    album_mbid,

    scrobbled_at,
    scrobbled_at_uts,
    track_url,

    run_id AS source_run_id,
    source_page,
    source_position,
    source_file,
    ingested_at

FROM ranked

WHERE duplicate_rank = 1;
