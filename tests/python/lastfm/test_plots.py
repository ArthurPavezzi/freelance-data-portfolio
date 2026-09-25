from pathlib import Path

import duckdb
from lastfm.plots import plot_genre_seasonality_yearly_heatmaps


def test_plot_genre_seasonality_yearly_heatmaps_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    output_dir = tmp_path / "figures"

    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE mart_genre_yearly (
                canonical_genre VARCHAR,
                weighted_scrobbles DOUBLE
            )
            """
        )

        connection.execute(
            """
            INSERT INTO mart_genre_yearly
            VALUES
                ('rock', 600.0),
                ('jazz', 400.0)
            """
        )

        connection.execute(
            """
            CREATE TABLE mart_genre_seasonality_yearly (
                season_year INTEGER,
                season_order INTEGER,
                season_name VARCHAR,
                canonical_genre VARCHAR,
                seasonality_index_season_year DOUBLE,
                season_year_genre_weighted_scrobbles DOUBLE,
                season_year_total_scrobbles BIGINT,
                is_full_season_year BOOLEAN
            )
            """
        )

        connection.execute(
            """
            INSERT INTO mart_genre_seasonality_yearly
            VALUES
                (2025, 1, 'Summer', 'rock', 0.80, 600.0, 1000, TRUE),
                (2025, 2, 'Autumn', 'rock', 1.10, 600.0, 1000, TRUE),
                (2025, 3, 'Winter', 'rock', 1.20, 600.0, 1000, TRUE),
                (2025, 4, 'Spring', 'rock', 0.90, 600.0, 1000, TRUE),

                (2025, 1, 'Summer', 'jazz', 1.15, 400.0, 1000, TRUE),
                (2025, 2, 'Autumn', 'jazz', 0.95, 400.0, 1000, TRUE),
                (2025, 3, 'Winter', 'jazz', 0.85, 400.0, 1000, TRUE),
                (2025, 4, 'Spring', 'jazz', 1.05, 400.0, 1000, TRUE)
            """
        )

    output_path = plot_genre_seasonality_yearly_heatmaps(
        db_path=db_path,
        output_dir=output_dir,
        top_n=25,
        include_incomplete_years=False,
        min_year_scrobbles=500,
    )

    assert output_path == output_dir / "genre_seasonality_yearly_heatmaps_top25.png"
    assert output_path.exists()
    assert output_path.stat().st_size > 0
