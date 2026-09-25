CREATE OR REPLACE TABLE mart_listening_by_hour_temporal AS

WITH classified AS (
    SELECT
        CAST(
            DATE_TRUNC(
                'month',
                listening_date
            ) AS DATE
        ) AS month_start,

        listening_year,

        CAST(
            EXTRACT(
                MONTH FROM listening_date
            ) AS INTEGER
        ) AS listening_month,

        CASE
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) = 12
                THEN listening_year + 1
            ELSE listening_year
        END AS season_year,

        CASE
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (12, 1, 2)
                THEN 1
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (3, 4, 5)
                THEN 2
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (6, 7, 8)
                THEN 3
            ELSE 4
        END AS season_order,

        CASE
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (12, 1, 2)
                THEN 'Summer'
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (3, 4, 5)
                THEN 'Autumn'
            WHEN
                EXTRACT(
                    MONTH FROM listening_date
                ) IN (6, 7, 8)
                THEN 'Winter'
            ELSE 'Spring'
        END AS season_name,

        weekday_iso,
        weekday_name,
        listening_hour,
        listening_date

    FROM fact_scrobble
),

hourly AS (
    SELECT
        month_start,
        listening_year,
        listening_month,
        season_year,
        season_order,
        season_name,
        weekday_iso,
        weekday_name,
        listening_hour,

        COUNT(*) AS scrobble_count,

        COUNT(
            DISTINCT listening_date
        ) AS active_days

    FROM classified

    GROUP BY
        month_start,
        listening_year,
        listening_month,
        season_year,
        season_order,
        season_name,
        weekday_iso,
        weekday_name,
        listening_hour
)

SELECT
    month_start,
    listening_year,
    listening_month,
    season_year,
    season_order,
    season_name,
    weekday_iso,
    weekday_name,
    listening_hour,
    scrobble_count,
    active_days,

    ROUND(
        scrobble_count / NULLIF(active_days, 0), 2
    ) AS avg_scrobbles_per_active_day,

    ROUND(
        100.0
        * scrobble_count
        / SUM(
            scrobble_count
        ) OVER (
            PARTITION BY month_start
        ),
        4
    ) AS scrobble_share_within_month_pct

FROM hourly

ORDER BY
    month_start,
    weekday_iso,
    listening_hour;
