CREATE OR REPLACE TABLE mart_listening_sessions AS

WITH ordered AS (
    SELECT
        scrobble_id,
        artist_id,
        track_id,
        album_id,
        scrobbled_at_local,
        listening_date,

        LAG(scrobbled_at_local) OVER (
            ORDER BY
                scrobbled_at_local,
                scrobble_id
        ) AS previous_scrobble_at

    FROM fact_scrobble
),

session_flags AS (
    SELECT
        *,

        CASE
            WHEN previous_scrobble_at IS NULL THEN 1

            WHEN
                scrobbled_at_local
                - previous_scrobble_at
                > INTERVAL '30 minutes'
                THEN 1

            ELSE 0
        END AS is_session_start

    FROM ordered
),

sessionized AS (
    SELECT
        *,

        SUM(is_session_start) OVER (
            ORDER BY
                scrobbled_at_local,
                scrobble_id
            ROWS BETWEEN
            UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) AS session_number

    FROM session_flags
),

aggregated AS (
    SELECT
        session_number,

        MIN(scrobbled_at_local) AS session_start_at,

        MAX(scrobbled_at_local) AS session_end_at,

        COUNT(*) AS scrobble_count,

        COUNT(DISTINCT artist_id) AS distinct_artists,

        COUNT(DISTINCT track_id) AS distinct_tracks,

        COUNT(DISTINCT album_id) AS distinct_albums

    FROM sessionized

    GROUP BY
        session_number
)

SELECT
    MD5(
        CAST(session_number AS VARCHAR)
        || '|'
        || CAST(
            session_start_at
            AS VARCHAR
        )
    ) AS session_id,

    session_number,
    session_start_at,
    session_end_at,

    DATE_DIFF(
        'second',
        session_start_at,
        session_end_at
    ) AS session_span_seconds,

    DATE_DIFF(
        'second',
        session_start_at,
        session_end_at
    ) / 60.0
        AS session_span_minutes,

    scrobble_count,
    distinct_artists,
    distinct_tracks,
    distinct_albums

FROM aggregated

ORDER BY
    session_start_at;
