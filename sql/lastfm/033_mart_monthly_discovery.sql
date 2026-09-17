CREATE OR REPLACE TABLE mart_monthly_discovery AS

WITH artist_first_month AS (
    SELECT
        artist_id,

        CAST(
            DATE_TRUNC(
                'month',
                MIN(
                    listening_date
                )
            )
            AS DATE
        ) AS first_month

    FROM fact_scrobble

    GROUP BY
        artist_id
),

monthly_artist_activity AS (
    SELECT
        CAST(
            DATE_TRUNC(
                'month',
                fact.listening_date
            )
            AS DATE
        ) AS month_start,

        fact.artist_id,

        COUNT(*) AS scrobble_count

    FROM fact_scrobble AS fact

    GROUP BY
        month_start,
        fact.artist_id
),

monthly AS (
    SELECT
        activity.month_start,

        SUM(
            activity.scrobble_count
        ) AS scrobble_count,

        COUNT(*) AS active_artists,

        COUNT(*) FILTER (
            WHERE
            first_seen.first_month
            = activity.month_start
        ) AS new_artists,

        SUM(
            activity.scrobble_count
        ) FILTER (
            WHERE
            first_seen.first_month
            = activity.month_start
        ) AS new_artist_scrobbles

    FROM
        monthly_artist_activity
            AS activity

    INNER JOIN
        artist_first_month
            AS first_seen
        ON activity.artist_id = first_seen.artist_id

    GROUP BY
        activity.month_start
),

final AS (
    SELECT
        month_start,
        scrobble_count,
        active_artists,
        new_artists,

        active_artists
        - new_artists
            AS returning_artists,

        COALESCE(
            new_artist_scrobbles,
            0
        ) AS new_artist_scrobbles,

        SUM(
            new_artists
        ) OVER (
            ORDER BY month_start
            ROWS BETWEEN
            UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) AS cumulative_artists

    FROM monthly
)

SELECT
    *,

    ROUND(
        100.0
        * new_artists
        / NULLIF(
            active_artists,
            0
        ),
        2
    ) AS discovery_rate_pct,

    ROUND(
        100.0
        * new_artist_scrobbles
        / NULLIF(
            scrobble_count,
            0
        ),
        2
    ) AS new_artist_scrobble_share_pct

FROM final

ORDER BY
    month_start;
