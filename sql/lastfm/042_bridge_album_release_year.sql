CREATE OR REPLACE TABLE bridge_album_release_year AS

WITH lastfm_year_tags AS (
    SELECT
        album_id,

        COUNT(
            DISTINCT TRY_CAST(
                tag_norm AS INTEGER
            )
        ) AS lastfm_candidate_year_count,

        MIN(
            TRY_CAST(
                tag_norm AS INTEGER
            )
        ) AS lastfm_candidate_year

    FROM bronze_album_tags

    WHERE
        REGEXP_FULL_MATCH(
            tag_norm,
            '^(19|20)[0-9]{2}$'
        )
        AND TRY_CAST(
            tag_norm AS INTEGER
        ) BETWEEN
        1900
        AND EXTRACT(
            YEAR FROM CURRENT_DATE
        )

    GROUP BY
        album_id
),

evidence AS (
    SELECT
        album.album_id,

        mb_release.first_release_year
            AS musicbrainz_release_year,

        mb_release.resolution_method
            AS musicbrainz_resolution_method,

        COALESCE(
            tags.lastfm_candidate_year_count,
            0
        ) AS lastfm_candidate_year_count,

        CASE
            WHEN
                tags.lastfm_candidate_year_count = 1
                THEN tags.lastfm_candidate_year
        END AS lastfm_release_year

    FROM dim_album AS album

    LEFT JOIN bronze_album_release_dates AS mb_release
        ON
            album.album_id
            = mb_release.album_id

    LEFT JOIN lastfm_year_tags AS tags
        ON
            album.album_id
            = tags.album_id
),

resolved AS (
    SELECT
        album_id,

        musicbrainz_release_year,
        musicbrainz_resolution_method,

        lastfm_candidate_year_count,
        lastfm_release_year,

        CASE
            WHEN
                musicbrainz_release_year
                IS NOT NULL
                THEN musicbrainz_release_year

            WHEN
                lastfm_candidate_year_count = 1
                THEN lastfm_release_year
        END AS release_year,

        CASE
            WHEN
                musicbrainz_release_year
                IS NOT NULL
                THEN 'musicbrainz'

            WHEN
                lastfm_candidate_year_count = 1
                THEN 'lastfm_year_tag'

            ELSE 'unknown'
        END AS release_year_source

    FROM evidence
)

SELECT
    album_id,

    release_year,

    CASE
        WHEN release_year IS NOT NULL
            THEN CAST(
                FLOOR(
                    release_year / 10.0
                ) * 10
                AS INTEGER
            )
    END AS release_decade,

    release_year_source,

    release_year IS NOT NULL
        AS has_release_year,

    musicbrainz_release_year,
    musicbrainz_resolution_method,

    lastfm_candidate_year_count,
    lastfm_release_year,

    (
        musicbrainz_release_year IS NOT NULL
        AND lastfm_release_year IS NOT NULL
    ) AS both_sources_available,

    CASE
        WHEN
            musicbrainz_release_year IS NOT NULL
            AND lastfm_release_year IS NOT NULL
            THEN
                musicbrainz_release_year
                = lastfm_release_year
    END AS exact_year_match,

    CASE
        WHEN
            musicbrainz_release_year IS NOT NULL
            AND lastfm_release_year IS NOT NULL
            THEN
                FLOOR(
                    musicbrainz_release_year / 10.0
                )
                =
                FLOOR(
                    lastfm_release_year / 10.0
                )
    END AS same_decade,

    CASE
        WHEN
            musicbrainz_release_year IS NOT NULL
            AND lastfm_release_year IS NOT NULL
            THEN
                FLOOR(
                    musicbrainz_release_year / 10.0
                )
                !=
                FLOOR(
                    lastfm_release_year / 10.0
                )
    END AS release_decade_conflict

FROM resolved;
