CREATE OR REPLACE TABLE dim_album AS

SELECT
    MD5(
        CONCAT_WS(
            '|',
            artist_norm,
            album_norm
        )
    ) AS album_id,

    MD5(artist_norm) AS artist_id,
    artist_norm,
    album_norm,
    ARG_MAX(album, scrobbled_at_uts) AS album_name,
    MAX(album_mbid)
        FILTER (WHERE album_mbid IS NOT NULL) AS album_mbid,
    MIN(scrobbled_at) AS first_scrobble_at,
    MAX(scrobbled_at)AS latest_scrobble_at,
    COUNT(*) AS scrobble_count

FROM stg_scrobbles
WHERE album_norm IS NOT NULL
GROUP BY
    artist_norm,
    album_norm;
