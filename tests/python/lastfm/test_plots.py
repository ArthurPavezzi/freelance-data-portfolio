from pathlib import Path

from lastfm.plots import plot_genre_seasonality_yearly_heatmaps


def test_plot_genre_seasonality_yearly_heatmaps_creates_file(tmp_path: Path) -> None:
    output_path = plot_genre_seasonality_yearly_heatmaps(
        output_dir=tmp_path, top_n=25, include_incomplete_years=False, min_year_scrobbles=500
    )

    assert output_path.exists()
    assert output_path.suffix == ".png"
    assert output_path.stat().st_size > 0
