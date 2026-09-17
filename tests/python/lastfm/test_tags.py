from lastfm.tags import (
    normalize_tag,
    parse_album_tags,
    parse_artist_tags,
)


def test_normalize_tag():
    assert normalize_tag("  Progressive   ROCK ") == "progressive rock"


def test_parse_album_tags():
    payload = {
        "toptags": {
            "tag": [
                {
                    "name": ("Progressive Rock"),
                    "count": 100,
                },
                {
                    "name": "Art Rock",
                    "count": 25,
                },
            ]
        }
    }

    result = parse_album_tags(
        "album-123",
        payload,
    )

    assert len(result) == 2

    assert result[0].album_id == ("album-123")
    assert result[0].tag_raw == ("Progressive Rock")
    assert result[0].tag_norm == ("progressive rock")
    assert result[0].weight == 100
    assert result[0].rank == 1

    assert result[1].tag_norm == ("art rock")
    assert result[1].weight == 25
    assert result[1].rank == 2


def test_parse_artist_tags():
    payload = {
        "toptags": {
            "tag": [
                {
                    "name": "Progressive Rock",
                    "count": 100,
                },
                {
                    "name": "Hard Rock",
                    "count": 40,
                },
            ]
        }
    }

    result = parse_artist_tags(
        "artist-123",
        payload,
    )

    assert len(result) == 2

    assert result[0].artist_id == ("artist-123")
    assert result[0].tag_norm == ("progressive rock")
    assert result[0].weight == 100
    assert result[0].rank == 1

    assert result[1].tag_norm == ("hard rock")
    assert result[1].weight == 40
