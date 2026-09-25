CREATE OR REPLACE TABLE mart_listening_by_decade AS

WITH classified_scrobbles AS (
    SELECT
        fact.scrobble_id,
        fact.artist_id,
        fact.track_id,
        fact.album_id,

        album_release.release_year,
        album_release.release_decade,
        album_release.release_year_source

    FROM fact_scrobble AS fact

    LEFT JOIN bridge_album_release_year AS album_release
        ON
            fact.album_id = album_release.album_id
),

coverage AS (
    SELECT
        COUNT(*) AS total_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NOT NULL
        ) AS scrobbles_with_album,

        COUNT(*) FILTER (
            WHERE release_year IS NOT NULL
        ) AS release_year_covered_scrobbles,

        COUNT(*) FILTER (
            WHERE
            album_id IS NOT NULL
            AND release_year IS NULL
        ) AS release_year_unknown_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NULL
        ) AS scrobbles_without_album

    FROM classified_scrobbles
),

decade_stats AS (
    SELECT
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
        ) AS distinct_artists,

        MIN(
            release_year
        ) AS earliest_release_year,

        MAX(
            release_year
        ) AS latest_release_year

    FROM classified_scrobbles

    WHERE
        release_decade IS NOT NULL

    GROUP BY
        release_decade
)

SELECT
    stats.release_decade,

    CAST(
        stats.release_decade
        AS VARCHAR
    ) || 's'
        AS release_decade_label,

    stats.scrobble_count,

    stats.distinct_tracks,
    stats.distinct_albums,
    stats.distinct_artists,

    stats.earliest_release_year,
    stats.latest_release_year,

    RANK() OVER (
        ORDER BY
            stats.scrobble_count DESC,
            stats.release_decade ASC
    ) AS decade_rank,

    stats.scrobble_count
    / NULLIF(
        coverage.release_year_covered_scrobbles,
        0
    )
        AS share_of_resolved_scrobbles,

    stats.scrobble_count
    / NULLIF(
        coverage.scrobbles_with_album,
        0
    )
        AS share_of_album_scrobbles,

    stats.scrobble_count
    / NULLIF(
        coverage.total_scrobbles,
        0
    )
        AS share_of_all_scrobbles,

    coverage.total_scrobbles,

    coverage.scrobbles_with_album,

    coverage.release_year_covered_scrobbles,

    coverage.release_year_unknown_scrobbles,

    coverage.scrobbles_without_album,

    coverage.release_year_covered_scrobbles
    / NULLIF(
        coverage.scrobbles_with_album,
        0
    )
        AS release_year_coverage,

    coverage.release_year_covered_scrobbles
    / NULLIF(
        coverage.total_scrobbles,
        0
    )
        AS release_year_dataset_coverage

FROM decade_stats AS stats

CROSS JOIN coverage;
