CREATE OR REPLACE TABLE mart_listening_by_hour AS

WITH hourly AS (
    SELECT
        weekday_iso,
        weekday_name,
        listening_hour,

        COUNT(*) AS scrobble_count,

        COUNT(
            DISTINCT listening_date
        ) AS active_days

    FROM fact_scrobble

    GROUP BY
        weekday_iso,
        weekday_name,
        listening_hour
)

SELECT
    weekday_iso,
    weekday_name,
    listening_hour,
    scrobble_count,
    active_days,

    ROUND(
        scrobble_count
        / NULLIF(
            active_days,
            0
        ),
        2
    ) AS avg_scrobbles_per_active_day,

    ROUND(
        100.0
        * scrobble_count
        / SUM(
            scrobble_count
        ) OVER (),
        4
    ) AS scrobble_share_pct

FROM hourly

ORDER BY
    weekday_iso,
    listening_hour;
