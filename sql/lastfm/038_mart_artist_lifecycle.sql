CREATE OR REPLACE TABLE mart_artist_lifecycle AS

WITH observed_months AS (
    SELECT
        distinct_months.month_start,

        ROW_NUMBER() OVER (
            ORDER BY
                distinct_months.month_start ASC
        ) AS observed_month_index

    FROM (
        SELECT DISTINCT
            CAST(
                DATE_TRUNC(
                    'month',
                    listening_date
                ) AS DATE
            ) AS month_start

        FROM fact_scrobble
    ) AS distinct_months
),

dataset_bounds AS (
    SELECT
        MIN(listening_date) AS dataset_first_date,
        MAX(listening_date) AS dataset_latest_date,

        MIN(
            CAST(
                DATE_TRUNC(
                    'month',
                    listening_date
                ) AS DATE
            )
        ) AS dataset_first_month,

        MAX(
            CAST(
                DATE_TRUNC(
                    'month',
                    listening_date
                ) AS DATE
            )
        ) AS dataset_latest_month

    FROM fact_scrobble
),

artist_summary AS (
    SELECT
        fact.artist_id,

        COUNT(*) AS total_scrobbles,

        COUNT(
            DISTINCT fact.listening_date
        ) AS active_days,

        COUNT(
            DISTINCT CAST(
                DATE_TRUNC(
                    'month',
                    fact.listening_date
                ) AS DATE
            )
        ) AS active_months,

        COUNT(
            DISTINCT fact.listening_year
        ) AS active_years,

        MIN(
            fact.listening_date
        ) AS first_observed_date,

        MAX(
            fact.listening_date
        ) AS last_observed_date,

        MIN(
            CAST(
                DATE_TRUNC(
                    'month',
                    fact.listening_date
                ) AS DATE
            )
        ) AS first_observed_month,

        MAX(
            CAST(
                DATE_TRUNC(
                    'month',
                    fact.listening_date
                ) AS DATE
            )
        ) AS last_observed_month

    FROM fact_scrobble AS fact

    GROUP BY
        fact.artist_id
),

artist_year AS (
    SELECT
        artist_id,
        listening_year,

        COUNT(*) AS scrobbles

    FROM fact_scrobble

    GROUP BY
        artist_id,
        listening_year
),

peak_year AS (
    SELECT
        ranked_years.artist_id,
        ranked_years.listening_year AS peak_year,
        ranked_years.scrobbles AS peak_year_scrobbles

    FROM (
        SELECT
            artist_id,
            listening_year,
            scrobbles,

            ROW_NUMBER() OVER (
                PARTITION BY artist_id
                ORDER BY
                    scrobbles DESC,
                    listening_year ASC
            ) AS year_rank

        FROM artist_year
    ) AS ranked_years

    WHERE
        ranked_years.year_rank = 1
),

artist_month AS (
    SELECT
        fact.artist_id,

        CAST(
            DATE_TRUNC(
                'month',
                fact.listening_date
            ) AS DATE
        ) AS month_start,

        COUNT(*) AS scrobbles

    FROM fact_scrobble AS fact

    GROUP BY
        fact.artist_id,
        month_start
),

peak_month AS (
    SELECT
        ranked_months.artist_id,
        ranked_months.month_start AS peak_month,
        ranked_months.scrobbles AS peak_month_scrobbles

    FROM (
        SELECT
            artist_id,
            month_start,
            scrobbles,

            ROW_NUMBER() OVER (
                PARTITION BY artist_id
                ORDER BY
                    scrobbles DESC,
                    month_start ASC
            ) AS month_rank

        FROM artist_month
    ) AS ranked_months

    WHERE
        ranked_months.month_rank = 1
),

artist_observed_months AS (
    SELECT
        monthly_artist.artist_id,
        monthly_artist.month_start,
        observed.observed_month_index,

        LAG(
            observed.observed_month_index
        ) OVER (
            PARTITION BY
                monthly_artist.artist_id
            ORDER BY
                observed.observed_month_index ASC
        ) AS previous_observed_month_index

    FROM artist_month AS monthly_artist

    INNER JOIN observed_months AS observed
        ON
            monthly_artist.month_start
            = observed.month_start
),

artist_gap_summary AS (
    SELECT
        artist_id,

        COALESCE(
            MAX(
                observed_month_index
                - previous_observed_month_index
                - 1
            ),
            0
        ) AS longest_inactive_observed_months

    FROM artist_observed_months

    GROUP BY
        artist_id
),

artist_last_index AS (
    SELECT
        artist_id,

        MAX(
            observed_month_index
        ) AS last_observed_month_index

    FROM artist_observed_months

    GROUP BY
        artist_id
),

latest_observed_index AS (
    SELECT
        MAX(
            observed_month_index
        ) AS latest_observed_month_index

    FROM observed_months
)

SELECT
    artist_stats.artist_id,
    artist_dim.artist_name,

    artist_stats.total_scrobbles,
    artist_stats.active_days,
    artist_stats.active_months,
    artist_stats.active_years,

    artist_stats.first_observed_date,
    artist_stats.last_observed_date,
    artist_stats.first_observed_month,
    artist_stats.last_observed_month,

    DATE_DIFF(
        'day',
        artist_stats.first_observed_date,
        artist_stats.last_observed_date
    ) AS observed_span_days,

    peak_year.peak_year,
    peak_year.peak_year_scrobbles,

    peak_month.peak_month,
    peak_month.peak_month_scrobbles,

    gap.longest_inactive_observed_months,

    latest.latest_observed_month_index
    - last_index.last_observed_month_index
        AS observed_months_since_last,

    artist_stats.first_observed_month
    = bounds.dataset_first_month
        AS first_seen_in_dataset_opening_month,

    artist_stats.last_observed_month
    = bounds.dataset_latest_month
        AS active_in_latest_observed_month

FROM artist_summary AS artist_stats

INNER JOIN dim_artist AS artist_dim
    ON
        artist_stats.artist_id
        = artist_dim.artist_id

INNER JOIN peak_year
    ON
        artist_stats.artist_id
        = peak_year.artist_id

INNER JOIN peak_month
    ON
        artist_stats.artist_id
        = peak_month.artist_id

INNER JOIN artist_gap_summary AS gap
    ON
        artist_stats.artist_id
        = gap.artist_id

INNER JOIN artist_last_index AS last_index
    ON
        artist_stats.artist_id
        = last_index.artist_id

CROSS JOIN latest_observed_index AS latest

CROSS JOIN dataset_bounds AS bounds;
