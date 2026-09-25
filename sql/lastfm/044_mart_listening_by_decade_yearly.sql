CREATE OR REPLACE TABLE mart_listening_by_decade_yearly AS

WITH classified_scrobbles AS (
    SELECT
        fact.scrobble_id,
        fact.artist_id,
        fact.track_id,
        fact.album_id,
        fact.listening_date,
        fact.listening_year,
        fact.listening_month,

        album_release.release_year,
        album_release.release_decade

    FROM fact_scrobble AS fact

    LEFT JOIN bridge_album_release_year AS album_release
        ON
            fact.album_id
            = album_release.album_id
),

year_coverage AS (
    SELECT
        listening_year,

        COUNT(*) AS year_total_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NOT NULL
        ) AS year_scrobbles_with_album,

        COUNT(*) FILTER (
            WHERE release_year IS NOT NULL
        ) AS year_release_year_covered_scrobbles,

        COUNT(*) FILTER (
            WHERE
            album_id IS NOT NULL
            AND release_year IS NULL
        ) AS year_release_year_unknown_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NULL
        ) AS year_scrobbles_without_album,

        COUNT(
            DISTINCT listening_month
        ) AS months_observed,

        COUNT(
            DISTINCT listening_date
        ) AS active_days,

        MIN(
            listening_date
        ) AS first_listening_date,

        MAX(
            listening_date
        ) AS last_listening_date

    FROM classified_scrobbles

    GROUP BY
        listening_year
),

decade_year_stats AS (
    SELECT
        listening_year,
        release_decade,

        COUNT(*) AS scrobble_count,

        COUNT(
            DISTINCT track_id
        ) AS distinct_tracks,

        COUNT(
            DISTINCT album_id
        ) AS distinct_albums,

        COUNT(
            DISTINCT artist_id
        ) AS distinct_artists

    FROM classified_scrobbles

    WHERE
        release_decade IS NOT NULL

    GROUP BY
        listening_year,
        release_decade
),

ranked AS (
    SELECT
        stats.*,

        RANK() OVER (
            PARTITION BY
                stats.listening_year

            ORDER BY
                stats.scrobble_count DESC,
                stats.release_decade ASC
        ) AS decade_rank_in_year

    FROM decade_year_stats AS stats
)

SELECT
    ranked.listening_year,

    ranked.release_decade,

    CAST(
        ranked.release_decade
        AS VARCHAR
    ) || 's'
        AS release_decade_label,

    ranked.scrobble_count,

    ranked.distinct_tracks,
    ranked.distinct_albums,
    ranked.distinct_artists,

    ranked.decade_rank_in_year,

    ranked.scrobble_count
    / NULLIF(
        coverage.year_release_year_covered_scrobbles,
        0
    )
        AS decade_share_within_resolved_year,

    ranked.scrobble_count
    / NULLIF(
        coverage.year_total_scrobbles,
        0
    )
        AS decade_share_within_full_year,

    coverage.year_total_scrobbles,

    coverage.year_scrobbles_with_album,

    coverage.year_release_year_covered_scrobbles,

    coverage.year_release_year_unknown_scrobbles,

    coverage.year_scrobbles_without_album,

    coverage.year_release_year_covered_scrobbles
    / NULLIF(
        coverage.year_scrobbles_with_album,
        0
    )
        AS release_year_coverage,

    coverage.year_release_year_covered_scrobbles
    / NULLIF(
        coverage.year_total_scrobbles,
        0
    )
        AS release_year_dataset_coverage,

    coverage.months_observed,

    coverage.active_days,

    coverage.first_listening_date,

    coverage.last_listening_date,

    coverage.months_observed = 12
        AS is_full_calendar_year

FROM ranked

INNER JOIN year_coverage AS coverage
    ON
        ranked.listening_year
        = coverage.listening_year;
