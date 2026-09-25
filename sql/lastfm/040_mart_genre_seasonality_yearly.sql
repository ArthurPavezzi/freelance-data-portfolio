CREATE OR REPLACE TABLE mart_genre_seasonality_yearly AS

WITH raw_scrobbles AS (
    SELECT
        fact.scrobble_id,
        fact.album_id,
        fact.listening_date,

        CASE
            WHEN EXTRACT(MONTH FROM fact.listening_date) = 12
                THEN fact.listening_year + 1
            ELSE fact.listening_year
        END AS season_year,

        CASE
            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (12, 1, 2)
                THEN 1

            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (3, 4, 5)
                THEN 2

            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (6, 7, 8)
                THEN 3

            ELSE 4
        END AS season_order,

        CASE
            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (12, 1, 2)
                THEN 'Summer'

            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (3, 4, 5)
                THEN 'Autumn'

            WHEN
                EXTRACT(
                    MONTH FROM fact.listening_date
                ) IN (6, 7, 8)
                THEN 'Winter'

            ELSE 'Spring'
        END AS season_name

    FROM fact_scrobble AS fact
),

raw_season_totals AS (
    SELECT
        raw_row.season_year,
        raw_row.season_order,
        raw_row.season_name,

        COUNT(*) AS season_total_scrobbles,

        COUNT(
            DISTINCT raw_row.listening_date
        ) AS season_active_days,

        COUNT(
            DISTINCT CAST(
                DATE_TRUNC(
                    'month',
                    raw_row.listening_date
                ) AS DATE
            )
        ) AS season_observed_months

    FROM raw_scrobbles AS raw_row

    GROUP BY
        raw_row.season_year,
        raw_row.season_order,
        raw_row.season_name
),

raw_season_year_totals AS (
    SELECT
        raw_row.season_year,

        COUNT(*) AS season_year_total_scrobbles,

        COUNT(
            DISTINCT raw_row.listening_date
        ) AS season_year_active_days,

        COUNT(
            DISTINCT CAST(
                DATE_TRUNC(
                    'month',
                    raw_row.listening_date
                ) AS DATE
            )
        ) AS months_observed_in_season_year,

        COUNT(
            DISTINCT raw_row.season_order
        ) AS seasons_observed_in_season_year

    FROM raw_scrobbles AS raw_row

    GROUP BY
        raw_row.season_year
),

classified_scrobbles AS (
    SELECT
        raw_row.scrobble_id,
        raw_row.listening_date,
        raw_row.season_year,
        raw_row.season_order,
        raw_row.season_name,
        genre.canonical_genre,
        genre.genre_weight

    FROM raw_scrobbles AS raw_row

    INNER JOIN bridge_album_genre_weight AS genre
        ON
            raw_row.album_id
            = genre.album_id
),

classified_season_genre AS (
    SELECT
        classified_row.season_year,
        classified_row.season_order,
        classified_row.season_name,
        classified_row.canonical_genre,

        SUM(classified_row.genre_weight) AS season_genre_weighted_scrobbles,

        COUNT(
            DISTINCT classified_row.scrobble_id
        ) AS season_genre_distinct_scrobbles

    FROM classified_scrobbles AS classified_row

    GROUP BY
        classified_row.season_year,
        classified_row.season_order,
        classified_row.season_name,
        classified_row.canonical_genre
),

classified_season_totals AS (
    SELECT
        classified_row.season_year,
        classified_row.season_order,
        classified_row.season_name,

        SUM(
            classified_row.genre_weight
        ) AS season_covered_scrobbles,

        COUNT(
            DISTINCT classified_row.scrobble_id
        ) AS season_covered_distinct_scrobbles

    FROM classified_scrobbles AS classified_row

    GROUP BY
        classified_row.season_year,
        classified_row.season_order,
        classified_row.season_name
),

classified_season_year_genre AS (
    SELECT
        classified_row.season_year,
        classified_row.canonical_genre,

        SUM(classified_row.genre_weight) AS season_year_genre_weighted_scrobbles,

        COUNT(
            DISTINCT classified_row.scrobble_id
        ) AS season_year_genre_distinct_scrobbles

    FROM classified_scrobbles AS classified_row

    GROUP BY
        classified_row.season_year,
        classified_row.canonical_genre
),

classified_season_year_totals AS (
    SELECT
        classified_row.season_year,

        SUM(classified_row.genre_weight) AS season_year_covered_scrobbles,

        COUNT(
            DISTINCT classified_row.scrobble_id
        ) AS season_year_covered_distinct_scrobbles

    FROM classified_scrobbles AS classified_row

    GROUP BY
        classified_row.season_year
),

season_year_genre_ranks AS (
    SELECT
        yearly.season_year,
        yearly.canonical_genre,
        yearly.season_year_genre_weighted_scrobbles,

        ROW_NUMBER() OVER (
            PARTITION BY
                yearly.season_year
            ORDER BY
                yearly.season_year_genre_weighted_scrobbles DESC,
                yearly.canonical_genre ASC
        ) AS genre_rank_in_season_year

    FROM classified_season_year_genre AS yearly
)

SELECT
    season_genre.season_year,
    season_genre.season_order,
    season_genre.season_name,
    season_genre.canonical_genre,

    ranks.genre_rank_in_season_year,

    raw_season.season_total_scrobbles,
    raw_season.season_active_days,
    raw_season.season_observed_months,

    raw_year.season_year_total_scrobbles,
    raw_year.season_year_active_days,
    raw_year.months_observed_in_season_year,
    raw_year.seasons_observed_in_season_year,

    (
        raw_year.months_observed_in_season_year = 12
        AND raw_year.seasons_observed_in_season_year = 4
    ) AS is_full_season_year,

    season_total.season_covered_scrobbles,
    season_total.season_covered_distinct_scrobbles,

    year_total.season_year_covered_scrobbles,
    year_total.season_year_covered_distinct_scrobbles,

    season_genre.season_genre_weighted_scrobbles,
    season_genre.season_genre_distinct_scrobbles,

    year_genre.season_year_genre_weighted_scrobbles,
    year_genre.season_year_genre_distinct_scrobbles,

    season_genre.season_genre_weighted_scrobbles
    / NULLIF(season_total.season_covered_scrobbles, 0) AS season_share,

    year_genre.season_year_genre_weighted_scrobbles
    / NULLIF(year_total.season_year_covered_scrobbles, 0) AS season_year_share,

    (
        season_genre.season_genre_weighted_scrobbles
        / NULLIF(season_total.season_covered_scrobbles, 0)
    )
    / NULLIF(
        year_genre.season_year_genre_weighted_scrobbles
        / NULLIF(year_total.season_year_covered_scrobbles, 0),
        0
    ) AS seasonality_index_season_year

FROM classified_season_genre AS season_genre

INNER JOIN classified_season_totals AS season_total
    ON
        season_genre.season_year = season_total.season_year
        AND season_genre.season_order = season_total.season_order

INNER JOIN classified_season_year_genre AS year_genre
    ON
        season_genre.season_year = year_genre.season_year
        AND season_genre.canonical_genre = year_genre.canonical_genre

INNER JOIN classified_season_year_totals AS year_total
    ON
        season_genre.season_year = year_total.season_year

INNER JOIN raw_season_totals AS raw_season
    ON
        season_genre.season_year = raw_season.season_year
        AND season_genre.season_order = raw_season.season_order

INNER JOIN raw_season_year_totals AS raw_year
    ON
        season_genre.season_year = raw_year.season_year

INNER JOIN season_year_genre_ranks AS ranks
    ON
        season_genre.season_year = ranks.season_year
        AND season_genre.canonical_genre = ranks.canonical_genre;
