CREATE OR REPLACE TABLE dim_artist AS

SELECT
    MD5(artist_norm) AS artist_id,
    artist_norm,
    ARG_MAX(artist, scrobbled_at_uts) AS artist_name,
    MAX(artist_mbid)
    FILTER (WHERE artist_mbid IS NOT NULL)
        AS artist_mbid,
    MIN(scrobbled_at) AS first_scrobble_at,
    MAX(scrobbled_at) AS latest_scrobble_at,
    COUNT(*) AS scrobble_count

FROM stg_scrobbles

GROUP BY
    artist_norm;
