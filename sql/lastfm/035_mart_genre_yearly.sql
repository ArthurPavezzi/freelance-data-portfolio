CREATE OR REPLACE TABLE mart_genre_yearly AS

WITH yearly_summary AS (
    SELECT
        listening_year,

        COUNT(*) AS total_scrobbles,

        COUNT(*) FILTER (
            WHERE album_id IS NOT NULL
        ) AS scrobbles_with_album,

        COUNT(
            DISTINCT listening_date
        ) AS active_days

    FROM fact_scrobble

    GROUP BY
        listening_year
),

covered_scrobbles AS (
    SELECT DISTINCT
        fact.scrobble_id,
        fact.listening_year

    FROM fact_scrobble AS fact

    INNER JOIN
        bridge_album_genre_weight
            AS genre
        ON
            fact.album_id
            = genre.album_id
),

yearly_coverage AS (
    SELECT
        listening_year,
        COUNT(*) AS genre_covered_scrobbles

    FROM covered_scrobbles

    GROUP BY
        listening_year
),

genre_year AS (
    SELECT
        fact.listening_year,
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
        fact.listening_year,
        genre.canonical_genre
),

genre_share AS (
    SELECT
        listening_year,
        canonical_genre,
        weighted_scrobbles,
        active_albums,
        active_artists,

        weighted_scrobbles
        / SUM(
            weighted_scrobbles
        ) OVER (
            PARTITION BY listening_year
        ) AS genre_share

    FROM genre_year
)

SELECT
    genre.listening_year,
    genre.canonical_genre,
    genre.weighted_scrobbles,
    genre.genre_share,
    genre.active_albums,
    genre.active_artists,
    coverage.genre_covered_scrobbles,
    yearly.total_scrobbles,
    yearly.scrobbles_with_album,
    yearly.active_days,

    coverage.genre_covered_scrobbles::DOUBLE
    / yearly.total_scrobbles AS genre_coverage

FROM genre_share AS genre

INNER JOIN yearly_coverage AS coverage
    ON
        genre.listening_year
        = coverage.listening_year

INNER JOIN yearly_summary AS yearly
    ON
        genre.listening_year
        = yearly.listening_year;
