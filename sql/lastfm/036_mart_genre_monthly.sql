CREATE OR REPLACE TABLE mart_genre_monthly AS

WITH monthly_summary AS (
    SELECT
        CAST(
            DATE_TRUNC(
                'month',
                listening_date
            ) AS DATE
        ) AS month_start,

        COUNT(*) AS total_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NOT NULL
        ) AS scrobbles_with_album,

        COUNT(
            DISTINCT listening_date
        ) AS active_days

    FROM fact_scrobble

    GROUP BY
        month_start
),

covered_scrobbles AS (
    SELECT DISTINCT
        fact.scrobble_id,

        CAST(
            DATE_TRUNC(
                'month',
                fact.listening_date
            ) AS DATE
        ) AS month_start

    FROM fact_scrobble AS fact

    INNER JOIN
        bridge_album_genre_weight
            AS genre
        ON
            fact.album_id
            = genre.album_id
),

monthly_coverage AS (
    SELECT
        month_start,

        COUNT(*) AS genre_covered_scrobbles

    FROM covered_scrobbles

    GROUP BY
        month_start
),

genre_month AS (
    SELECT
        CAST(
            DATE_TRUNC(
                'month',
                fact.listening_date
            ) AS DATE
        ) AS month_start,

        genre.canonical_genre,

        SUM(
            genre.genre_weight
        ) AS weighted_scrobbles,

        COUNT(
            DISTINCT fact.album_id
        ) AS active_albums,

        COUNT(
            DISTINCT genre.artist_id
        ) AS active_artists

    FROM fact_scrobble AS fact

    INNER JOIN
        bridge_album_genre_weight
            AS genre
        ON
            fact.album_id
            = genre.album_id

    GROUP BY
        month_start,
        genre.canonical_genre
),

genre_share AS (
    SELECT
        month_start,
        canonical_genre,
        weighted_scrobbles,
        active_albums,
        active_artists,

        weighted_scrobbles
        / SUM(weighted_scrobbles) OVER (PARTITION BY month_start) AS genre_share

    FROM genre_month
)

SELECT
    genre.month_start,

    CAST(EXTRACT(
        YEAR FROM genre.month_start
    ) AS INTEGER) AS listening_year,

    CAST(EXTRACT(
        MONTH FROM genre.month_start
    ) AS INTEGER) AS listening_month,

    genre.canonical_genre,
    genre.weighted_scrobbles,
    genre.genre_share,
    genre.active_albums,
    genre.active_artists,
    coverage.genre_covered_scrobbles,
    monthly.total_scrobbles,
    monthly.scrobbles_with_album,
    monthly.active_days,

    CAST(coverage.genre_covered_scrobbles AS DOUBLE)
    / monthly.total_scrobbles AS genre_coverage

FROM genre_share AS genre

INNER JOIN monthly_coverage AS coverage
    ON
        genre.month_start
        = coverage.month_start

INNER JOIN monthly_summary AS monthly
    ON
        genre.month_start
        = monthly.month_start;
