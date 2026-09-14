CREATE OR REPLACE TABLE dim_track AS

SELECT
    MD5(
        CONCAT_WS(
            '|',
            artist_norm,
            track_norm
        )
    ) AS track_id,

    MD5(artist_norm) AS artist_id,
    artist_norm,
    track_norm,
    ARG_MAX(track, scrobbled_at_uts) AS track_name,
    MAX(track_mbid)
        FILTER (WHERE track_mbid IS NOT NULL) AS track_mbid,
    MIN(scrobbled_at) AS first_scrobble_at,
    MAX(scrobbled_at) AS latest_scrobble_at,
    COUNT(*) AS scrobble_count,
    COUNT(DISTINCT album_norm) 
    	FILTER (WHERE album_norm IS NOT NULL) AS album_count

FROM stg_scrobbles
GROUP BY
    artist_norm,
    track_norm;
