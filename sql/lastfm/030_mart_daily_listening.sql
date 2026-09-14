CREATE OR REPLACE TABLE mart_daily_listening AS

SELECT
    listening_date,
    COUNT(*) AS scrobble_count,
    COUNT(DISTINCT artist_id) AS distinct_artists,
    COUNT(DISTINCT track_id) AS distinct_tracks,
    COUNT(DISTINCT album_id) AS distinct_albums,
    COUNT(DISTINCT listening_hour) AS active_hours,
    MIN(scrobbled_at_local) AS first_scrobble_at_local,
    MAX(scrobbled_at_local) AS latest_scrobble_at_local

FROM fact_scrobble
GROUP BY listening_date
ORDER BY listening_date;
