CREATE OR REPLACE TABLE mart_artist_summary AS

WITH artist_activity AS (
    SELECT
        artist_id,
        COUNT(*) AS scrobble_count,
        COUNT(DISTINCT track_id) AS distinct_tracks,
        COUNT(DISTINCT album_id) AS distinct_albums,
        COUNT(DISTINCT listening_date) AS active_days,
        COUNT(
            DISTINCT DATE_TRUNC(
                'month',
                listening_date
            )
        ) AS active_months,
        MIN(scrobbled_at_local) AS first_scrobble_at_local,
        MAX(scrobbled_at_local) AS latest_scrobble_at_local

    FROM fact_scrobble
    GROUP BY artist_id
),

dataset_bounds AS (
    SELECT
        COUNT(*) AS total_scrobbles,
        MAX(listening_date) AS latest_listening_date
    FROM fact_scrobble
)

SELECT
    artist.artist_id,
    artist.artist_name,
    artist.artist_mbid,

    activity.scrobble_count,
    activity.distinct_tracks,
    activity.distinct_albums,
    activity.active_days,
    activity.active_months,

    activity.first_scrobble_at_local,
    activity.latest_scrobble_at_local,

    DATE_DIFF(
        'day',
        CAST(activity.latest_scrobble_at_local AS DATE),
        bounds.latest_listening_date
    ) AS days_since_last_scrobble,

    ROUND(
        100.0 * activity.scrobble_count / NULLIF(bounds.total_scrobbles, 0),
        4
    ) AS scrobble_share_pct

FROM artist_activity AS activity
INNER JOIN dim_artist AS artist ON activity.artist_id = artist.artist_id
CROSS JOIN dataset_bounds AS bounds
ORDER BY activity.scrobble_count DESC;
