CREATE OR REPLACE TABLE mart_artist_yearly AS

WITH yearly_totals AS (
    SELECT
        listening_year,

        COUNT(*) AS total_scrobbles,

        COUNT(
            DISTINCT listening_date
        ) AS dataset_active_days

    FROM fact_scrobble

    GROUP BY
        listening_year
),

artist_year_stats AS (
    SELECT
        fact.artist_id,
        fact.listening_year,

        COUNT(*) AS scrobbles,

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
            DISTINCT fact.track_id
        ) AS distinct_tracks,

        COUNT(
            DISTINCT fact.album_id
        ) FILTER (
            WHERE fact.album_id IS NOT NULL
        ) AS distinct_albums

    FROM fact_scrobble AS fact

    GROUP BY
        fact.artist_id,
        fact.listening_year
),

enriched AS (
    SELECT
        stats.artist_id,
        artist_dim.artist_name,
        stats.listening_year,
        stats.scrobbles,
        stats.active_days,
        stats.active_months,
        stats.distinct_tracks,
        stats.distinct_albums,

        yearly.total_scrobbles
            AS year_total_scrobbles,

        yearly.dataset_active_days,

        CAST(stats.scrobbles AS DOUBLE)
        / yearly.total_scrobbles
            AS year_scrobble_share,

        CAST(stats.scrobbles AS DOUBLE)
        / lifecycle.total_scrobbles
            AS artist_lifetime_share,

        stats.listening_year
        = lifecycle.peak_year
            AS is_peak_year,

        stats.listening_year
        = CAST(EXTRACT(
            YEAR
            FROM lifecycle.first_observed_date
        ) AS INTEGER)
            AS is_first_observed_year,

        stats.listening_year
        = CAST(EXTRACT(
            YEAR
            FROM lifecycle.last_observed_date
        ) AS INTEGER)
            AS is_last_observed_year

    FROM artist_year_stats AS stats

    INNER JOIN dim_artist AS artist_dim
        ON
            stats.artist_id
            = artist_dim.artist_id

    INNER JOIN yearly_totals AS yearly
        ON
            stats.listening_year
            = yearly.listening_year

    INNER JOIN
        mart_artist_lifecycle
            AS lifecycle
        ON
            stats.artist_id
            = lifecycle.artist_id
)

SELECT
    artist_id,
    artist_name,
    listening_year,
    scrobbles,
    active_days,
    active_months,
    distinct_tracks,
    distinct_albums,
    year_total_scrobbles,
    dataset_active_days,
    year_scrobble_share,
    artist_lifetime_share,
    is_peak_year,
    is_first_observed_year,
    is_last_observed_year,

    ROW_NUMBER() OVER (
        PARTITION BY listening_year
        ORDER BY
            scrobbles DESC,
            artist_name ASC
    ) AS artist_rank

FROM enriched;
