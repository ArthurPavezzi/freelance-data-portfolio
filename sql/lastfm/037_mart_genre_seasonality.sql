CREATE OR REPLACE TABLE mart_genre_seasonality AS

WITH latest_month AS (
    SELECT
        CAST(
            DATE_TRUNC('month', MAX(listening_date)) AS DATE
        ) AS latest_month_start

    FROM fact_scrobble
),

observed_months AS (
    SELECT DISTINCT
        monthly.month_start,
        monthly.listening_year,
        monthly.listening_month,

        CASE
            WHEN monthly.listening_month = 12
                THEN monthly.listening_year + 1
            ELSE monthly.listening_year
        END AS season_year,

        monthly.genre_covered_scrobbles,
        monthly.total_scrobbles,
        monthly.active_days,
        monthly.genre_coverage

    FROM mart_genre_monthly AS monthly

    WHERE
        monthly.month_start
        < (
            SELECT latest.latest_month_start
            FROM latest_month AS latest
        )
),

genres AS (
    SELECT DISTINCT canonical_genre

    FROM bridge_album_genre_weight
),

month_genre_grid AS (
    SELECT
        monthly.month_start,
        monthly.season_year,
        monthly.listening_month,
        genre.canonical_genre,

        CASE
            WHEN
                monthly.listening_month
                IN (12, 1, 2)
                THEN 1

            WHEN
                monthly.listening_month
                IN (3, 4, 5)
                THEN 2

            WHEN
                monthly.listening_month
                IN (6, 7, 8)
                THEN 3

            ELSE 4
        END AS season_order,

        CASE
            WHEN
                monthly.listening_month
                IN (12, 1, 2)
                THEN 'Summer'

            WHEN
                monthly.listening_month
                IN (3, 4, 5)
                THEN 'Autumn'

            WHEN
                monthly.listening_month
                IN (6, 7, 8)
                THEN 'Winter'

            ELSE 'Spring'
        END AS season_name,

        COALESCE(genre_month.weighted_scrobbles, 0.0) AS weighted_scrobbles,

        COALESCE(genre_month.genre_share, 0.0) AS genre_share,

        monthly.genre_covered_scrobbles,
        monthly.total_scrobbles,
        monthly.active_days,
        monthly.genre_coverage

    FROM observed_months AS monthly

    CROSS JOIN genres AS genre

    LEFT JOIN
        mart_genre_monthly
            AS genre_month
        ON
            monthly.month_start = genre_month.month_start
            AND genre.canonical_genre = genre_month.canonical_genre
),

genre_baseline AS (
    SELECT
        canonical_genre,

        AVG(genre_share) AS mean_monthly_genre_share

    FROM month_genre_grid

    GROUP BY
        canonical_genre
),

season_summary AS (
    SELECT
        canonical_genre,
        season_order,
        season_name,

        COUNT(*) AS observed_months,

        COUNT(DISTINCT season_year) AS observed_years,

        SUM(active_days) AS total_active_days,

        AVG(genre_coverage) AS mean_genre_coverage,

        AVG(genre_share) AS mean_monthly_genre_share,

        SUM(weighted_scrobbles) AS weighted_scrobbles,

        SUM(weighted_scrobbles)
        / NULLIF(SUM(genre_covered_scrobbles), 0) AS volume_weighted_genre_share

    FROM month_genre_grid

    GROUP BY
        canonical_genre,
        season_order,
        season_name
)

SELECT
    season.canonical_genre,
    season.season_order,
    season.season_name,
    season.observed_months,
    season.observed_years,
    season.total_active_days,
    season.mean_genre_coverage,
    season.mean_monthly_genre_share,
    season.weighted_scrobbles,
    season.volume_weighted_genre_share,

    season.mean_monthly_genre_share
    / NULLIF(baseline.mean_monthly_genre_share, 0) AS seasonality_index

FROM season_summary AS season

INNER JOIN genre_baseline AS baseline
    ON
        season.canonical_genre
        = baseline.canonical_genre;
