CREATE OR REPLACE TABLE fact_scrobble AS

WITH localized AS (
    SELECT
        *,

        TIMEZONE(
            'UTC',
            scrobbled_at
        ) AS scrobbled_at_utc,

        TIMEZONE(
            'America/Sao_Paulo',
            scrobbled_at
        ) AS scrobbled_at_local

    FROM stg_scrobbles
)

SELECT
    scrobble_id,

    MD5(
        artist_norm
    ) AS artist_id,

    MD5(
        CONCAT_WS(
            '|',
            artist_norm,
            track_norm
        )
    ) AS track_id,

    CASE
        WHEN album_norm IS NULL
            THEN NULL
        ELSE MD5(
            CONCAT_WS(
                '|',
                artist_norm,
                album_norm
            )
        )
    END AS album_id,

    scrobbled_at_utc,
    scrobbled_at_local,

    CAST(scrobbled_at_local AS DATE) AS listening_date,

    EXTRACT(YEAR FROM scrobbled_at_local) AS listening_year,

    EXTRACT(MONTH FROM scrobbled_at_local) AS listening_month,

    EXTRACT(HOUR FROM scrobbled_at_local) AS listening_hour,

    EXTRACT(ISODOW FROM scrobbled_at_local) AS weekday_iso,

    STRFTIME(scrobbled_at_local, '%A') AS weekday_name,

    source_run_id,
    source_page,
    source_position,
    source_file,
    ingested_at

FROM localized;
