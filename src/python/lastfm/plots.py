import math
from pathlib import Path

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import PercentFormatter

DEFAULT_DB_PATH = Path("data/processed/lastfm/lastfm.duckdb")
DEFAULT_FIGURE_DIR = Path("figures/lastfm")
DEFAULT_COMPARISON_START = pd.Timestamp("2020-01-01")
DEFAULT_COMPARISON_END = pd.Timestamp("2025-12-31")


def _pretty_genre_label(genre: str) -> str:
    special = {"mpb": "MPB", "r&b": "R&B"}

    return special.get(genre, genre.title())


def load_yearly_genres(
    connection: duckdb.DuckDBPyConnection, *, top_n: int = 10
) -> tuple[pd.DataFrame, list[str]]:
    genre_totals = connection.execute(
        """
        SELECT
            canonical_genre,

            SUM(
                weighted_scrobbles
            ) AS total_weighted_scrobbles

        FROM mart_genre_yearly

        GROUP BY
            canonical_genre

        ORDER BY
            total_weighted_scrobbles DESC,
            canonical_genre ASC
        """
    ).df()

    top_genres = genre_totals.head(top_n)["canonical_genre"].tolist()

    yearly = connection.execute(
        """
        SELECT
            listening_year,
            canonical_genre,
            weighted_scrobbles

        FROM mart_genre_yearly

        ORDER BY
            listening_year,
            canonical_genre
        """
    ).df()

    yearly["genre_group"] = yearly["canonical_genre"].where(
        yearly["canonical_genre"].isin(top_genres), "Other"
    )

    collapsed = yearly.groupby(["listening_year", "genre_group"], as_index=False)[
        "weighted_scrobbles"
    ].sum()

    collapsed["year_total"] = collapsed.groupby("listening_year")["weighted_scrobbles"].transform(
        "sum"
    )

    collapsed["genre_share"] = collapsed["weighted_scrobbles"] / collapsed["year_total"]

    return (collapsed, top_genres)


def _contiguous_year_blocks(pivot: pd.DataFrame) -> list[tuple[int, int]]:
    valid_years = pivot.index[pivot.notna().any(axis=1)].astype(int).tolist()

    if not valid_years:
        return []

    blocks: list[tuple[int, int]] = []

    block_start = valid_years[0]
    previous_year = valid_years[0]

    for year in valid_years[1:]:
        if year == previous_year + 1:
            previous_year = year
            continue

        blocks.append((block_start, previous_year))

        block_start = year
        previous_year = year

    blocks.append((block_start, previous_year))

    return blocks


def plot_genre_evolution(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR, top_n: int = 10
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data, top_genres = load_yearly_genres(connection, top_n=top_n)

    plot_order = ["Other", *top_genres]

    pivot = (
        data.pivot(index="listening_year", columns="genre_group", values="genre_share")
        .reindex(columns=plot_order)
        .fillna(0.0)
    )

    all_years = pd.Index(
        range(int(pivot.index.min()), int(pivot.index.max()) + 1), name="listening_year"
    )

    pivot = pivot.reindex(all_years)

    blocks = _contiguous_year_blocks(pivot)

    figure, axis = plt.subplots(figsize=(12, 7))

    color_map = plt.get_cmap("tab20")

    colors = [color_map(index) for index in range(len(plot_order))]

    for block_index, (start_year, end_year) in enumerate(blocks):
        block = pivot.loc[start_year:end_year]

        x_values = block.index.to_numpy()

        y_values = [block[genre].to_numpy() for genre in plot_order]

        if block_index == 0:
            axis.stackplot(x_values, *y_values, labels=plot_order, colors=colors)
        else:
            axis.stackplot(x_values, *y_values, colors=colors)

    axis.set_title("Genre composition over time")

    axis.set_xlabel("Year")

    axis.set_ylabel("Share of genre-classified scrobbles")

    axis.set_ylim(0, 1)

    axis.set_xticks(all_years)

    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    handles, labels = axis.get_legend_handles_labels()

    handle_by_genre = dict(zip(labels, handles, strict=True))

    legend_order = [*top_genres, "Other"]

    axis.legend(
        [handle_by_genre[genre] for genre in legend_order],
        [_pretty_genre_label(genre) for genre in legend_order],
        title="Genre",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
    )

    figure.tight_layout()

    output_path = output_dir / "genre_evolution_yearly.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_artist_year_heatmap(
    connection: duckdb.DuckDBPyConnection, *, top_n: int = 25
) -> tuple[pd.DataFrame, list[str], list[int]]:
    top_artists = connection.execute(
        """
        WITH artist_totals AS (
            SELECT
                artist_id,
                ANY_VALUE(
                    artist_name
                ) AS artist_name,

                SUM(
                    scrobbles
                ) AS total_scrobbles

            FROM mart_artist_yearly

            GROUP BY
                artist_id
        )

        SELECT
            artist_id,
            artist_name,
            total_scrobbles

        FROM artist_totals

        ORDER BY
            total_scrobbles DESC,
            artist_name ASC

        LIMIT ?
        """,
        [top_n],
    ).df()

    yearly = connection.execute(
        """
        SELECT
            artist_id,
            artist_name,
            listening_year,
            year_scrobble_share

        FROM mart_artist_yearly
        """
    ).df()

    observed_years = [
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT
                listening_year

            FROM mart_artist_yearly

            ORDER BY
                listening_year
            """
        ).fetchall()
    ]

    selected = yearly[yearly["artist_id"].isin(top_artists["artist_id"])].copy()

    artist_order = top_artists["artist_name"].tolist()

    matrix = pd.DataFrame(0.0, index=artist_order, columns=observed_years)

    for row in selected.itertuples(index=False):
        matrix.loc[row.artist_name, row.listening_year] = row.year_scrobble_share

    all_years = list(range(min(observed_years), max(observed_years) + 1))

    matrix = matrix.reindex(columns=all_years)

    return (matrix, artist_order, all_years)


def plot_artist_year_heatmap(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    top_n: int = 25,
    annotation_threshold_pct: float = 5.0,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (matrix, artist_order, all_years) = load_artist_year_heatmap(connection, top_n=top_n)

    values = matrix.to_numpy() * 100.0

    figure, axis = plt.subplots(figsize=(13, 10))

    image = axis.imshow(values, aspect="auto")

    for row_index in range(len(artist_order)):
        for column_index in range(len(all_years)):
            value = values[row_index, column_index]

            if pd.notna(value) and value >= annotation_threshold_pct:
                axis.text(
                    column_index, row_index, f"{value:.1%}", ha="center", va="center", fontsize=8
                )

    axis.set_title("Top artists over time")

    axis.set_xlabel("Year")

    axis.set_ylabel("Artist")

    axis.set_xticks(range(len(all_years)))

    axis.set_xticklabels(all_years)

    axis.set_yticks(range(len(artist_order)))

    axis.set_yticklabels(artist_order)

    colorbar = figure.colorbar(image, ax=axis, pad=0.02)

    colorbar.set_label("Share of yearly scrobbles (%)")

    figure.tight_layout()

    output_path = output_dir / "artist_year_heatmap_top25.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_artist_lifetime_heatmap(
    connection: duckdb.DuckDBPyConnection, *, top_n: int = 25
) -> tuple[pd.DataFrame, list[str], list[int]]:
    top_artists = connection.execute(
        """
        WITH artist_totals AS (
            SELECT
                artist_id,

                ANY_VALUE(
                    artist_name
                ) AS artist_name,

                SUM(
                    scrobbles
                ) AS total_scrobbles

            FROM mart_artist_yearly

            GROUP BY
                artist_id
        )

        SELECT
            artist_id,
            artist_name,
            total_scrobbles

        FROM artist_totals

        ORDER BY
            total_scrobbles DESC,
            artist_name ASC

        LIMIT ?
        """,
        [top_n],
    ).df()

    yearly = connection.execute(
        """
        SELECT
            artist_id,
            artist_name,
            listening_year,
            artist_lifetime_share

        FROM mart_artist_yearly
        """
    ).df()

    observed_years = [
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT
                listening_year

            FROM mart_artist_yearly

            ORDER BY
                listening_year
            """
        ).fetchall()
    ]

    selected = yearly[yearly["artist_id"].isin(top_artists["artist_id"])].copy()

    artist_order = top_artists["artist_name"].tolist()

    matrix = pd.DataFrame(0.0, index=artist_order, columns=observed_years)

    for row in selected.itertuples(index=False):
        matrix.loc[row.artist_name, row.listening_year] = row.artist_lifetime_share

    all_years = list(range(min(observed_years), max(observed_years) + 1))

    matrix = matrix.reindex(columns=all_years)

    return (matrix, artist_order, all_years)


def plot_artist_lifetime_heatmap(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    top_n: int = 25,
    annotation_threshold_pct: float = 20.0,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        matrix, artist_order, all_years = load_artist_lifetime_heatmap(connection, top_n=top_n)

    values = matrix.to_numpy() * 100.0

    figure, axis = plt.subplots(figsize=(13, 10))

    image = axis.imshow(values, aspect="auto")

    for row_index in range(len(artist_order)):
        for column_index in range(len(all_years)):
            value = values[row_index, column_index]

            if pd.notna(value) and value >= annotation_threshold_pct:
                axis.text(
                    column_index, row_index, f"{value:.0%}", ha="center", va="center", fontsize=8
                )

    axis.set_title("Artist listening concentration over time")

    axis.set_xlabel("Year")

    axis.set_ylabel("Artist")

    axis.set_xticks(range(len(all_years)))

    axis.set_xticklabels(all_years)

    axis.set_yticks(range(len(artist_order)))

    axis.set_yticklabels(artist_order)

    colorbar = figure.colorbar(image, ax=axis, pad=0.02)

    colorbar.set_label("Share of artist's lifetime scrobbles (%)")

    figure.tight_layout()

    output_path = output_dir / "artist_lifetime_heatmap_top25.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_genre_seasonality_heatmap(
    connection: duckdb.DuckDBPyConnection, *, top_n: int = 25
) -> tuple[pd.DataFrame, list[str], list[str]]:
    top_genres = connection.execute(
        """
        WITH genre_totals AS (
            SELECT
                canonical_genre,

                SUM(
                    weighted_scrobbles
                ) AS total_weighted_scrobbles

            FROM mart_genre_yearly

            GROUP BY
                canonical_genre
        )

        SELECT
            canonical_genre,
            total_weighted_scrobbles

        FROM genre_totals

        ORDER BY
            total_weighted_scrobbles DESC,
            canonical_genre ASC

        LIMIT ?
        """,
        [top_n],
    ).df()

    seasonality = connection.execute(
        """
        SELECT
            canonical_genre,
            season_order,
            season_name,
            seasonality_index

        FROM mart_genre_seasonality

        ORDER BY
            canonical_genre,
            season_order
        """
    ).df()

    genre_order = top_genres["canonical_genre"].tolist()

    season_order = ["Summer", "Autumn", "Winter", "Spring"]

    selected = seasonality[seasonality["canonical_genre"].isin(genre_order)].copy()

    matrix = selected.pivot(
        index="canonical_genre", columns="season_name", values="seasonality_index"
    ).reindex(index=genre_order, columns=season_order)

    return matrix, genre_order, season_order


def plot_genre_seasonality_heatmap(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR, top_n: int = 25
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (matrix, genre_order, season_order) = load_genre_seasonality_heatmap(
            connection, top_n=top_n
        )

    values = matrix.to_numpy()

    finite_values = values[pd.notna(values)]

    value_min = min(float(finite_values.min()), 1.0)

    value_max = max(float(finite_values.max()), 1.0)

    figure, axis = plt.subplots(figsize=(9, 11))

    normalization = TwoSlopeNorm(vmin=value_min, vcenter=1.0, vmax=value_max)

    image = axis.imshow(values, aspect="auto", norm=normalization, cmap="coolwarm")

    for row_index in range(len(genre_order)):
        for column_index in range(len(season_order)):
            value = values[row_index, column_index]

            if pd.notna(value):
                axis.text(
                    column_index, row_index, f"{value:.2f}×", ha="center", va="center", fontsize=8
                )

    axis.set_title("Genre seasonality")

    axis.set_xlabel("Season")

    axis.set_ylabel("Genre")

    axis.set_xticks(range(len(season_order)))

    axis.set_xticklabels(season_order)

    axis.set_yticks(range(len(genre_order)))

    axis.set_yticklabels([_pretty_genre_label(genre) for genre in genre_order])

    colorbar = figure.colorbar(image, ax=axis, pad=0.02)

    colorbar.set_label("Seasonality index")

    figure.tight_layout()

    output_path = output_dir / "genre_seasonality_heatmap_top25.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_genre_seasonality_yearly_heatmap(
    connection: duckdb.DuckDBPyConnection,
    *,
    top_n: int = 25,
    include_incomplete_years: bool = False,
    min_year_scrobbles: int | None = 500,
) -> tuple[pd.DataFrame, list[str], list[int], list[str]]:
    top_genres = connection.execute(
        """
        WITH genre_totals AS (
            SELECT
                canonical_genre,

                SUM(
                    weighted_scrobbles
                ) AS total_weighted_scrobbles

            FROM mart_genre_yearly

            GROUP BY
                canonical_genre
        )

        SELECT
            canonical_genre

        FROM genre_totals

        ORDER BY
            total_weighted_scrobbles DESC,
            canonical_genre ASC

        LIMIT ?
        """,
        [top_n],
    ).df()

    data = connection.execute(
        """
        SELECT
            season_year,
            season_order,
            season_name,
            canonical_genre,
            seasonality_index_season_year,
            season_year_genre_weighted_scrobbles,
            season_year_total_scrobbles,
            is_full_season_year
    
        FROM mart_genre_seasonality_yearly
    
        ORDER BY
            season_year ASC,
            season_order ASC,
            canonical_genre ASC
        """
    ).df()

    genre_order = top_genres["canonical_genre"].tolist()

    filtered = data[data["canonical_genre"].isin(genre_order)].copy()

    if not include_incomplete_years:
        filtered = filtered[filtered["is_full_season_year"]].copy()

    if min_year_scrobbles is not None:
        filtered = filtered[filtered["season_year_total_scrobbles"] >= min_year_scrobbles].copy()

    season_year_order = sorted(filtered["season_year"].unique().tolist())

    season_order = ["Summer", "Autumn", "Winter", "Spring"]

    return filtered, genre_order, season_year_order, season_order


def plot_genre_seasonality_yearly_heatmaps(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    top_n: int = 25,
    include_incomplete_years: bool = False,
    min_year_scrobbles: int | None = 500,
    ncols: int = 3,
    min_genre_year_support: float = 25.0,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (data, genre_order, season_year_order, season_order) = (
            load_genre_seasonality_yearly_heatmap(
                connection,
                top_n=top_n,
                include_incomplete_years=(include_incomplete_years),
                min_year_scrobbles=(min_year_scrobbles),
            )
        )

    if not season_year_order:
        raise RuntimeError("No season years available after applying filters.")

    matrices: dict[int, pd.DataFrame] = {}

    for season_year in season_year_order:
        season_year_frame = data[data["season_year"] == season_year].copy()

        support = (
            season_year_frame.groupby("canonical_genre")["season_year_genre_weighted_scrobbles"]
            .first()
            .reindex(genre_order)
            .fillna(0.0)
        )

        matrix = season_year_frame.pivot(
            index="canonical_genre", columns="season_name", values="seasonality_index_season_year"
        ).reindex(index=genre_order, columns=season_order)

        observed_seasons = set(season_year_frame["season_name"])

        for season_name in observed_seasons:
            matrix[season_name] = matrix[season_name].fillna(0.0)

        for genre in genre_order:
            if support.loc[genre] < min_genre_year_support:
                matrix.loc[genre, :] = float("nan")

        low_support_genres = support[support < min_genre_year_support].index

        matrix.loc[low_support_genres, :] = float("nan")

        matrices[season_year] = matrix

    normalization = TwoSlopeNorm(vmin=0.5, vcenter=1.0, vmax=1.5)

    nrows = (len(season_year_order) + ncols - 1) // ncols

    figure, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(4 * ncols + 1.0, 0.15 * len(genre_order) * nrows + 1.0),
        squeeze=False,
    )

    image = None

    color_map = plt.get_cmap("bwr").with_extremes(bad="#8c8c8c")

    for panel_index, (axis, season_year) in enumerate(
        zip(axes.flatten(), season_year_order, strict=False)
    ):
        matrix = matrices[season_year]

        values = matrix.to_numpy()

        image = axis.imshow(values, aspect="auto", norm=normalization, cmap=color_map)

        for row_index in range(len(genre_order)):
            for column_index in range(len(season_order)):
                value = values[row_index, column_index]

                if pd.notna(value):
                    text_color = "white" if value <= 0.65 or value >= 1.35 else "black"

                    axis.text(
                        column_index,
                        row_index,
                        f"{value:.2f}×",
                        ha="center",
                        va="center",
                        fontsize=7.5,
                        color=text_color,
                    )

        season_year_total = int(
            data.loc[data["season_year"] == season_year, "season_year_total_scrobbles"].iloc[0]
        )

        axis.set_title(f"{season_year} (n={season_year_total:,})")

        axis.set_xticks(range(len(season_order)))
        axis.set_xticklabels(season_order)

        panel_column = panel_index % ncols

        axis.set_yticks(range(len(genre_order)))

        if panel_column == 0:
            axis.set_yticklabels([_pretty_genre_label(genre) for genre in genre_order])
        else:
            axis.set_yticklabels([])

    for axis in axes.flatten()[len(season_year_order) :]:
        axis.axis("off")

    figure.suptitle("Genre seasonality by year", y=0.995)

    figure.supxlabel("Season", y=0.035)

    figure.supylabel("Genre")

    figure.text(
        0.5,
        0.01,
        f"Grey cells indicate genre-years with <{min_genre_year_support:g} weighted scrobbles.",
        ha="center",
        fontsize=9,
    )

    figure.tight_layout()

    if image is not None:
        colorbar = figure.colorbar(
            image, ax=axes.ravel().tolist(), pad=0.01, shrink=0.92, extend="both"
        )

        colorbar.set_label("Seasonality index")

    output_path = output_dir / "genre_seasonality_yearly_heatmaps_top25.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_artist_lifecycle_lines(
    connection: duckdb.DuckDBPyConnection, *, top_n: int = 10
) -> tuple[pd.DataFrame, list[str], list[int]]:
    top_artists = connection.execute(
        """
        WITH artist_totals AS (
            SELECT
                artist_id,
                ANY_VALUE(
                    artist_name
                ) AS artist_name,
                SUM(
                    scrobbles
                ) AS total_scrobbles

            FROM mart_artist_yearly

            GROUP BY
                artist_id
        )

        SELECT
            artist_id,
            artist_name,
            total_scrobbles

        FROM artist_totals

        ORDER BY
            total_scrobbles DESC,
            artist_name ASC

        LIMIT ?
        """,
        [top_n],
    ).df()

    yearly = connection.execute(
        """
        SELECT
            artist_id,
            artist_name,
            listening_year,
            scrobbles,
            is_peak_year

        FROM mart_artist_yearly

        ORDER BY
            listening_year ASC,
            artist_name ASC
        """
    ).df()

    selected = yearly[yearly["artist_id"].isin(top_artists["artist_id"])].copy()

    artist_order = top_artists["artist_name"].tolist()

    observed_years = sorted(yearly["listening_year"].unique().tolist())

    all_years = list(range(min(observed_years), max(observed_years) + 1))

    observed_year_set = set(observed_years)

    rows: list[dict[str, object]] = []

    for artist_name in artist_order:
        artist_frame = selected[selected["artist_name"] == artist_name].set_index("listening_year")

        for year in all_years:
            if year not in observed_year_set:
                scrobbles = float("nan")
                is_peak_year = False

            elif year in artist_frame.index:
                scrobbles = float(artist_frame.loc[year, "scrobbles"])

                is_peak_year = bool(artist_frame.loc[year, "is_peak_year"])

            else:
                scrobbles = 0.0
                is_peak_year = False

            rows.append(
                {
                    "artist_name": artist_name,
                    "listening_year": year,
                    "scrobbles": scrobbles,
                    "is_peak_year": is_peak_year,
                }
            )

    data = pd.DataFrame(rows)

    return data, artist_order, all_years


def plot_artist_lifecycle_lines(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR, top_n: int = 10
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (data, artist_order, all_years) = load_artist_lifecycle_lines(connection, top_n=top_n)

    figure, axis = plt.subplots(figsize=(13, 7))

    color_map = plt.get_cmap("tab10")

    partial_years = [2014, 2015, 2016, 2019, 2026]

    for year in partial_years:
        axis.axvspan(year - 0.5, year + 0.5, alpha=0.06, color="black", zorder=0)

    for artist_index, artist_name in enumerate(artist_order):
        artist_frame = data[data["artist_name"] == artist_name].copy()

        color = color_map(artist_index % color_map.N)

        axis.plot(
            artist_frame["listening_year"],
            artist_frame["scrobbles"],
            marker="o",
            linewidth=2,
            markersize=4,
            label=artist_name,
            color=color,
        )

        peak_frame = artist_frame[artist_frame["is_peak_year"]]

        axis.scatter(
            peak_frame["listening_year"],
            peak_frame["scrobbles"],
            s=70,
            color=color,
            edgecolor="black",
            linewidth=0.8,
            zorder=5,
        )

    axis.set_title("Listening lifecycle of top artists")

    axis.set_xlabel("Year")

    axis.set_ylabel("Annual scrobbles")

    axis.set_xticks(all_years)

    axis.set_ylim(bottom=0)

    axis.grid(axis="y", alpha=0.25)

    axis.legend(title="Artist", bbox_to_anchor=(1.02, 1), loc="upper left")

    figure.text(
        0.5,
        0.01,
        (
            "2014, 2015, 2016, 2019 and 2026 are partial years; "
            "2017–2018 have no observed listening data. "
            "Large outlined markers indicate each artist's peak observed year."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.035, 1, 1))

    output_path = output_dir / "artist_lifecycle_lines_top10.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_artist_lifecycle_peak_normalized(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR, top_n: int = 10
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (data, artist_order, all_years) = load_artist_lifecycle_lines(connection, top_n=top_n)

    normalized = data.copy()

    normalized["peak_scrobbles"] = normalized.groupby("artist_name")["scrobbles"].transform("max")

    normalized["peak_index"] = 100.0 * normalized["scrobbles"] / normalized["peak_scrobbles"]

    figure, axis = plt.subplots(figsize=(13, 7))

    color_map = plt.get_cmap("tab10")

    partial_years = [2014, 2015, 2016, 2019, 2026]

    for year in partial_years:
        axis.axvspan(year - 0.5, year + 0.5, alpha=0.06, color="black", zorder=0)

    for artist_index, artist_name in enumerate(artist_order):
        artist_frame = normalized[normalized["artist_name"] == artist_name].copy()

        color = color_map(artist_index % color_map.N)

        axis.plot(
            artist_frame["listening_year"],
            artist_frame["peak_index"],
            marker="o",
            linewidth=2,
            markersize=4,
            label=artist_name,
            color=color,
        )

    axis.set_title("Listening lifecycle relative to each artist's peak")

    axis.set_xlabel("Year")

    axis.set_ylabel("Share of artist's peak year")

    axis.set_xticks(all_years)

    axis.set_ylim(0, 105)

    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100.0))

    axis.grid(axis="y", alpha=0.25)

    axis.legend(title="Artist", bbox_to_anchor=(1.02, 1), loc="upper left")

    figure.text(
        0.5,
        0.01,
        (
            "Each artist's peak observed year = 100%. "
            "2014, 2015, 2016, 2019 and 2026 are partial years; "
            "2017–2018 have no observed listening data."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.035, 1, 1))

    output_path = output_dir / "artist_lifecycle_peak_normalized_top10.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_hourly_listening(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    hourly = connection.execute(
        """
        SELECT
            listening_hour,
            COUNT(*) AS scrobbles

        FROM fact_scrobble

        GROUP BY
            listening_hour

        ORDER BY
            listening_hour
        """
    ).df()

    complete_hours = pd.DataFrame({"listening_hour": range(24)})

    hourly = complete_hours.merge(hourly, on="listening_hour", how="left")

    hourly["scrobbles"] = hourly["scrobbles"].fillna(0).astype(int)

    hourly["share"] = hourly["scrobbles"] / hourly["scrobbles"].sum()

    return hourly


def plot_hourly_circular_bars(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data = load_hourly_listening(connection)

    hours = data["listening_hour"].astype(int).tolist()

    shares = data["share"].astype(float).tolist()

    angles = [hour * 2.0 * math.pi / 24.0 for hour in hours]

    bar_width = 2.0 * math.pi / 24.0 * 0.88

    figure, axis = plt.subplots(figsize=(10, 10), subplot_kw={"projection": "polar"})

    axis.set_theta_zero_location("N")

    axis.set_theta_direction(-1)

    bars = axis.bar(angles, shares, width=bar_width, align="center", alpha=0.85)

    axis.set_xticks(angles)

    axis.set_xticklabels([f"{hour:02d}h" for hour in hours])

    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis.set_title("Listening rhythm across the day", pad=24)

    axis.grid(alpha=0.25)

    peak_index = int(data["share"].idxmax())

    for index, bar in enumerate(bars):
        if index == peak_index:
            bar.set_linewidth(1.5)
            bar.set_edgecolor("black")

    peak_hour = int(data.loc[peak_index, "listening_hour"])

    peak_share = float(data.loc[peak_index, "share"])

    axis.text(
        angles[peak_index],
        peak_share,
        f"{peak_hour:02d}h\n{peak_share:.1%}",
        ha="left",
        va="bottom",
        fontsize=7,
    )

    figure.text(
        0.5,
        0.02,
        (
            "Share of observed scrobbles by local listening hour "
            "(America/Sao_Paulo). Historical collection gaps may "
            "affect the aggregate pattern."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 1))

    output_path = output_dir / "hourly_listening_circular.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_hourly_listening_by_day_type(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    hourly = connection.execute(
        """
        SELECT
            CASE
                WHEN EXTRACT(
                    DOW FROM listening_date
                ) IN (0, 6)
                    THEN 'Weekend'
                ELSE 'Weekday'
            END AS day_type,

            listening_hour,

            COUNT(*) AS scrobbles

        FROM fact_scrobble

        GROUP BY
            day_type,
            listening_hour

        ORDER BY
            day_type,
            listening_hour
        """
    ).df()

    grid = pd.MultiIndex.from_product(
        [["Weekday", "Weekend"], range(24)], names=["day_type", "listening_hour"]
    ).to_frame(index=False)

    hourly = grid.merge(hourly, on=["day_type", "listening_hour"], how="left")

    hourly["scrobbles"] = hourly["scrobbles"].fillna(0).astype(int)

    hourly["share"] = hourly["scrobbles"] / hourly.groupby("day_type")["scrobbles"].transform("sum")

    return hourly


def plot_hourly_circular_bars_by_day_type(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data = load_hourly_listening_by_day_type(connection)

    hours = list(range(24))

    angles = [hour * 2.0 * math.pi / 24.0 for hour in hours]

    bar_width = 2.0 * math.pi / 24.0 * 0.88

    radial_max = float(data["share"].max())

    radial_max *= 1.08

    figure, axes = plt.subplots(
        nrows=1, ncols=2, figsize=(16, 8), subplot_kw={"projection": "polar"}
    )

    for axis, day_type in zip(axes, ["Weekday", "Weekend"], strict=True):
        day_data = (
            data[data["day_type"] == day_type].sort_values("listening_hour").reset_index(drop=True)
        )

        shares = day_data["share"].astype(float).tolist()

        bars = axis.bar(angles, shares, width=bar_width, align="center", alpha=0.85)

        axis.set_theta_zero_location("N")

        axis.set_theta_direction(-1)

        axis.set_ylim(0, radial_max)

        axis.set_xticks(angles)

        axis.set_xticklabels([f"{hour:02d}h" for hour in hours], fontsize=8)

        axis.tick_params(axis="y", labelsize=8)

        axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

        axis.grid(alpha=0.25)

        axis.set_title(day_type, pad=22, fontsize=11)

        peak_index = int(day_data["share"].idxmax())

        peak_hour = int(day_data.loc[peak_index, "listening_hour"])

        peak_share = float(day_data.loc[peak_index, "share"])

        bars[peak_index].set_linewidth(1.8)
        bars[peak_index].set_edgecolor("black")
        bars[peak_index].set_alpha(1.0)

        axis.text(
            angles[peak_index],
            peak_share * 0.72,
            f"{peak_hour:02d}h\n{peak_share:.1%}",
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color="white",
            zorder=5,
        )

    figure.suptitle("Listening rhythm: weekdays vs weekends", y=0.99)

    figure.text(
        0.5,
        0.02,
        ("Shares are normalized within each day type. Both panels use the same radial scale."),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 0.97))

    output_path = output_dir / "hourly_listening_weekday_weekend.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_hourly_listening_by_year(
    connection: duckdb.DuckDBPyConnection, *, min_year_scrobbles: int = 500
) -> tuple[pd.DataFrame, list[int]]:
    eligible_years = connection.execute(
        """
        WITH year_coverage AS (
            SELECT
                listening_year,

                COUNT(*) AS total_scrobbles,

                COUNT(
                    DISTINCT DATE_TRUNC(
                        'month',
                        listening_date
                    )
                ) AS observed_months

            FROM fact_scrobble

            GROUP BY
                listening_year
        )

        SELECT
            listening_year

        FROM year_coverage

        WHERE observed_months = 12
          AND total_scrobbles >= ?

        ORDER BY
            listening_year
        """,
        [min_year_scrobbles],
    ).df()

    year_order = eligible_years["listening_year"].astype(int).tolist()

    hourly = connection.execute(
        """
        SELECT
            listening_year,
            listening_hour,
            COUNT(*) AS scrobbles

        FROM fact_scrobble

        WHERE listening_year IN (
            SELECT
                listening_year

            FROM (
                SELECT
                    listening_year,
                    COUNT(*) AS total_scrobbles,

                    COUNT(
                        DISTINCT DATE_TRUNC(
                            'month',
                            listening_date
                        )
                    ) AS observed_months

                FROM fact_scrobble

                GROUP BY
                    listening_year
            ) AS year_coverage

            WHERE observed_months = 12
              AND total_scrobbles >= ?
        )

        GROUP BY
            listening_year,
            listening_hour

        ORDER BY
            listening_year,
            listening_hour
        """,
        [min_year_scrobbles],
    ).df()

    grid = pd.MultiIndex.from_product(
        [year_order, range(24)], names=["listening_year", "listening_hour"]
    ).to_frame(index=False)

    hourly = grid.merge(hourly, on=["listening_year", "listening_hour"], how="left")

    hourly["scrobbles"] = hourly["scrobbles"].fillna(0).astype(int)

    hourly["year_total"] = hourly.groupby("listening_year")["scrobbles"].transform("sum")

    hourly["share"] = hourly["scrobbles"] / hourly["year_total"]

    return (hourly, year_order)


def plot_hourly_circular_bars_by_year(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    min_year_scrobbles: int = 500,
    ncols: int = 3,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        (data, year_order) = load_hourly_listening_by_year(
            connection, min_year_scrobbles=min_year_scrobbles
        )

    if not year_order:
        raise RuntimeError("No complete years available.")

    hours = list(range(24))

    angles = [hour * 2.0 * math.pi / 24.0 for hour in hours]

    bar_width = 2.0 * math.pi / 24.0 * 0.88

    radial_max = float(data["share"].max()) * 1.08

    nrows = (len(year_order) + ncols - 1) // ncols

    figure, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(5.5 * ncols, 5.5 * nrows),
        subplot_kw={"projection": "polar"},
        squeeze=False,
    )

    for axis, listening_year in zip(axes.flatten(), year_order, strict=False):
        year_data = (
            data[data["listening_year"] == listening_year]
            .sort_values("listening_hour")
            .reset_index(drop=True)
        )

        shares = year_data["share"].astype(float).tolist()

        bars = axis.bar(angles, shares, width=bar_width, align="center", alpha=0.85)

        axis.set_theta_zero_location("N")

        axis.set_theta_direction(-1)

        axis.set_ylim(0, radial_max)

        axis.set_xticks(angles)

        axis.set_xticklabels([f"{hour:02d}h" for hour in hours], fontsize=7)

        axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

        axis.tick_params(axis="y", labelsize=7)

        axis.grid(alpha=0.25)

        year_total = int(year_data["year_total"].iloc[0])

        axis.set_title(f"{listening_year} (n={year_total:,})", pad=18, fontsize=11)

        peak_index = int(year_data["share"].idxmax())

        peak_hour = int(year_data.loc[peak_index, "listening_hour"])

        peak_share = float(year_data.loc[peak_index, "share"])

        bars[peak_index].set_linewidth(1.5)

        bars[peak_index].set_edgecolor("black")

        axis.text(
            angles[peak_index],
            peak_share,
            f"  {peak_hour:02d}h\n  {peak_share:.1%}",
            ha="left",
            va="bottom",
            fontsize=7,
        )

    for axis in axes.flatten()[len(year_order) :]:
        axis.axis("off")

    figure.suptitle("Listening rhythm by year", y=0.995)

    figure.text(
        0.5,
        0.015,
        (
            "Shares are normalized within each year. "
            "Only years with all 12 months observed are shown; "
            "all panels use the same radial scale."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.035, 1, 0.97))

    output_path = output_dir / "hourly_listening_by_year.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_listening_sessions(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT
            session_id,
            session_start_at,
            session_end_at,
            session_span_minutes,
            scrobble_count,
            distinct_artists,
            distinct_tracks,
            distinct_albums

        FROM mart_listening_sessions

        ORDER BY
            session_start_at
        """
    ).df()


def plot_session_size_distribution(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    session_sizes = sessions["scrobble_count"].astype(int)

    median_size = float(session_sizes.median())

    mean_size = float(session_sizes.mean())

    maximum_size = int(session_sizes.max())

    bucket_edges = [0, 1, 3, 5, 10, 20, 40, 80, float("inf")]

    bucket_labels = ["1", "2–3", "4–5", "6–10", "11–20", "21–40", "41–80", "81+"]

    buckets = pd.cut(
        session_sizes, bins=bucket_edges, labels=bucket_labels, include_lowest=True, right=True
    )

    bucket_counts = buckets.value_counts(sort=False).reindex(bucket_labels, fill_value=0)

    bucket_shares = bucket_counts / bucket_counts.sum()

    sorted_sizes = session_sizes.sort_values().reset_index(drop=True)

    cumulative_share = pd.Series(range(1, len(sorted_sizes) + 1), dtype=float) / len(sorted_sizes)

    figure, (axis_bars, axis_ecdf) = plt.subplots(nrows=1, ncols=2, figsize=(14, 6))

    bars = axis_bars.bar(bucket_labels, bucket_shares)

    axis_bars.set_title("Session size distribution")

    axis_bars.set_xlabel("Scrobbles per session")

    axis_bars.set_ylabel("Share of sessions")

    axis_bars.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis_bars.grid(axis="y", alpha=0.25)

    for bar, share in zip(bars, bucket_shares, strict=True):
        axis_bars.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{share:.1%}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    axis_ecdf.step(sorted_sizes, cumulative_share, where="post")

    axis_ecdf.set_title("Cumulative session-size distribution")

    axis_ecdf.set_xlabel("Scrobbles per session")

    axis_ecdf.set_ylabel("Cumulative share of sessions")

    axis_ecdf.set_xscale("log")

    ecdf_ticks = [1, 2, 5, 10, 20, 50, 100, 200]

    axis_ecdf.set_xticks([tick for tick in ecdf_ticks if tick <= max(200, maximum_size)])

    axis_ecdf.set_xticklabels([str(tick) for tick in ecdf_ticks if tick <= max(200, maximum_size)])

    axis_ecdf.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis_ecdf.grid(alpha=0.25)

    figure.suptitle("Listening session size", y=0.99)

    figure.text(
        0.5,
        0.015,
        (
            f"{len(sessions):,} observed sessions · "
            f"median {median_size:.0f} scrobbles · "
            f"mean {mean_size:.2f} · "
            f"maximum {maximum_size}"
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 0.95))

    output_path = output_dir / "session_size_distribution.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_session_span_distribution(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    spans = sessions["session_span_minutes"].astype(float)

    median_span = float(spans.median())

    mean_span = float(spans.mean())

    maximum_span = int(spans.max())

    bucket_edges = [-1, 0, 5, 15, 30, 60, 120, 240, float("inf")]

    bucket_labels = ["0", "1–5", "6–15", "16–30", "31–60", "61–120", "121–240", "241+"]

    buckets = pd.cut(spans, bins=bucket_edges, labels=bucket_labels, right=True)

    bucket_counts = buckets.value_counts(sort=False).reindex(bucket_labels, fill_value=0)

    bucket_shares = bucket_counts / bucket_counts.sum()

    sorted_spans = spans.sort_values().reset_index(drop=True)

    cumulative_share = pd.Series(range(1, len(sorted_spans) + 1), dtype=float) / len(sorted_spans)

    # +1 allows zero-minute sessions to be shown
    # on a logarithmic x-axis.
    log_positions = sorted_spans + 1

    figure, (axis_bars, axis_ecdf) = plt.subplots(nrows=1, ncols=2, figsize=(14, 6))

    bars = axis_bars.bar(bucket_labels, bucket_shares)

    axis_bars.set_title("Session span distribution")

    axis_bars.set_xlabel("Session span (minutes)")

    axis_bars.set_ylabel("Share of sessions")

    axis_bars.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis_bars.grid(axis="y", alpha=0.25)

    for bar, share in zip(bars, bucket_shares, strict=True):
        axis_bars.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{share:.1%}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    axis_ecdf.step(log_positions, cumulative_share, where="post")

    axis_ecdf.set_title("Cumulative session-span distribution")

    axis_ecdf.set_xlabel("Session span (minutes)")

    axis_ecdf.set_ylabel("Cumulative share of sessions")

    axis_ecdf.set_xscale("log")

    real_tick_values = [0, 1, 5, 15, 30, 60, 120, 240, 500]

    visible_ticks = [tick for tick in real_tick_values if tick <= max(500, maximum_span)]

    axis_ecdf.set_xticks([tick + 1 for tick in visible_ticks])

    axis_ecdf.set_xticklabels([str(tick) for tick in visible_ticks])

    axis_ecdf.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis_ecdf.grid(alpha=0.25)

    figure.suptitle("Listening session span", y=0.99)

    figure.text(
        0.5,
        0.015,
        (
            f"{len(sessions):,} observed sessions · "
            f"median {median_span:.0f} min · "
            f"mean {mean_span:.2f} min · "
            f"maximum {maximum_span} min"
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 0.95))

    output_path = output_dir / "session_span_distribution.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_session_size_vs_span(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    x_values = sessions["scrobble_count"].astype(float)

    span_minutes = sessions["session_span_minutes"].astype(float)

    y_values = span_minutes + 1.0

    figure, axis = plt.subplots(figsize=(10, 7))

    hexbin = axis.hexbin(
        x_values, y_values, gridsize=45, xscale="log", yscale="log", bins="log", mincnt=1
    )

    axis.set_title("Listening session size vs span")

    axis.set_xlabel("Scrobbles per session")

    axis.set_ylabel("Session span (minutes)")

    x_ticks = [1, 2, 5, 10, 20, 50, 100, 200]

    axis.set_xticks([tick for tick in x_ticks if tick <= x_values.max()])

    axis.set_xticklabels([str(tick) for tick in x_ticks if tick <= x_values.max()])

    span_ticks = [0, 1, 5, 15, 30, 60, 120, 240, 500]

    visible_span_ticks = [tick for tick in span_ticks if tick <= span_minutes.max()]

    axis.set_yticks([tick + 1 for tick in visible_span_ticks])

    axis.set_yticklabels([str(tick) for tick in visible_span_ticks])

    axis.grid(alpha=0.20)

    colorbar = figure.colorbar(hexbin, ax=axis, pad=0.02)

    colorbar.set_label("Session density (log count)")

    figure.text(
        0.5,
        0.015,
        (
            "Both axes use logarithmic spacing. "
            "Session span is plotted as span + 1 internally "
            "so zero-minute sessions remain visible."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 1))

    output_path = output_dir / "session_size_vs_span.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_session_size_vs_artist_diversity(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    x_values = sessions["scrobble_count"].astype(float)

    y_values = sessions["distinct_artists"].astype(float)

    figure, axis = plt.subplots(figsize=(10, 7))

    hexbin = axis.hexbin(
        x_values, y_values, gridsize=45, xscale="log", yscale="log", bins="log", mincnt=1
    )

    maximum = float(x_values.max())

    guide_x = pd.Series([1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, maximum], dtype=float)

    guide_x = guide_x[(guide_x >= 1.0) & (guide_x <= maximum)].drop_duplicates().sort_values()

    guide_specs = [
        (1.00, "artists / scrobbles = 1.00", "#4d4d4d", "-."),
        (0.50, "artists / scrobbles = 0.50", "#7a7a7a", "--"),
        (0.25, "artists / scrobbles = 0.25", "#aaaaaa", ":"),
    ]

    for ratio, label, color, linestyle in guide_specs:
        guide_y = guide_x * ratio

        valid = guide_y >= 1.0

        axis.plot(
            guide_x[valid],
            guide_y[valid],
            color=color,
            linestyle=linestyle,
            linewidth=1.4,
            alpha=0.9,
            label=label,
            zorder=3,
        )

    x_ticks = [1, 2, 5, 10, 20, 50, 100, 200]

    visible_x_ticks = [tick for tick in x_ticks if tick <= x_values.max()]

    axis.set_xticks(visible_x_ticks)

    axis.set_xticklabels([str(tick) for tick in visible_x_ticks])

    y_ticks = [1, 2, 5, 10, 20, 50]

    visible_y_ticks = [tick for tick in y_ticks if tick <= y_values.max()]

    axis.set_yticks(visible_y_ticks)

    axis.set_yticklabels([str(tick) for tick in visible_y_ticks])

    axis.set_title("Session size vs artist diversity")

    axis.set_xlabel("Scrobbles per session")

    axis.set_ylabel("Distinct artists per session")

    axis.grid(alpha=0.20)

    axis.legend(title="Diversity ratio", loc="upper left")

    colorbar = figure.colorbar(hexbin, ax=axis, pad=0.02)

    colorbar.set_label("Session density (log count)")

    figure.text(
        0.5,
        0.015,
        (
            "Both axes use logarithmic spacing. "
            "Dashed lines show constant ratios of "
            "distinct artists to scrobbles."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.045, 1, 1))

    output_path = output_dir / "session_size_vs_artist_diversity.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_artist_diversity_ratio_by_session_size(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    sessions = sessions[sessions["scrobble_count"] > 1].copy()

    sessions["diversity_ratio"] = sessions["distinct_artists"] / sessions["scrobble_count"]

    bucket_order = ["2–3", "4–5", "6–10", "11–20", "21–40", "41–80", "81+"]

    sessions["size_bucket"] = pd.cut(
        sessions["scrobble_count"],
        bins=[1, 3, 5, 10, 20, 40, 80, float("inf")],
        labels=bucket_order,
        right=True,
    )

    distributions = [
        sessions.loc[sessions["size_bucket"] == bucket, "diversity_ratio"].to_numpy()
        for bucket in bucket_order
    ]

    counts = [len(values) for values in distributions]

    medians = [float(pd.Series(values).median()) for values in distributions]

    figure, axis = plt.subplots(figsize=(11, 7))

    axis.boxplot(
        distributions,
        tick_labels=bucket_order,
        showfliers=False,
        widths=0.65,
        patch_artist=True,
        boxprops={"facecolor": "#bfd7ea", "edgecolor": "#4d4d4d", "linewidth": 1.2},
        medianprops={"color": "#1f4e79", "linewidth": 2.0},
        whiskerprops={"color": "#4d4d4d", "linewidth": 1.1},
        capprops={"color": "#4d4d4d", "linewidth": 1.1},
    )

    for index, median in enumerate(medians, start=1):
        axis.text(index, median + 0.025, f"{median:.0%}", ha="center", va="bottom", fontsize=9)

    axis.set_title("Artist diversity within listening sessions")

    axis.set_xlabel("Scrobbles per session")

    axis.set_ylabel("Distinct artists / scrobbles")

    axis.set_ylim(0, 1.05)

    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis.grid(axis="y", alpha=0.25)

    labels_with_counts = [
        f"{bucket}\n(n={count:,})" for bucket, count in zip(bucket_order, counts, strict=True)
    ]

    axis.set_xticklabels(labels_with_counts)

    figure.text(
        0.5,
        0.015,
        (
            "Sessions with one scrobble are excluded because their "
            "diversity ratio is mechanically 100%. "
            "Labels above boxes show median ratios; outliers are hidden."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.055, 1, 1))

    output_path = output_dir / "session_artist_diversity_ratio_by_size.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_session_content_diversity_by_size(
    *, db_path: Path = DEFAULT_DB_PATH, output_dir: Path = DEFAULT_FIGURE_DIR
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        sessions = load_listening_sessions(connection)

    sessions = sessions[sessions["scrobble_count"] > 1].copy()

    sessions["track_ratio"] = sessions["distinct_tracks"] / sessions["scrobble_count"]

    sessions["album_ratio"] = sessions["distinct_albums"] / sessions["scrobble_count"]

    sessions["artist_ratio"] = sessions["distinct_artists"] / sessions["scrobble_count"]

    bucket_order = ["2–3", "4–5", "6–10", "11–20", "21–40", "41–80", "81+"]

    sessions["size_bucket"] = pd.cut(
        sessions["scrobble_count"],
        bins=[1, 3, 5, 10, 20, 40, 80, float("inf")],
        labels=bucket_order,
        right=True,
    )

    rows: list[dict[str, object]] = []

    for bucket in bucket_order:
        bucket_data = sessions[sessions["size_bucket"] == bucket]

        rows.append(
            {
                "size_bucket": bucket,
                "sessions": len(bucket_data),
                "track_ratio": bucket_data["track_ratio"].median(),
                "album_ratio": bucket_data["album_ratio"].median(),
                "artist_ratio": bucket_data["artist_ratio"].median(),
            }
        )

    summary = pd.DataFrame(rows)

    x_positions = list(range(len(bucket_order)))

    figure, axis = plt.subplots(figsize=(11, 7))

    metric_specs = [
        ("track_ratio", "Distinct tracks", "o", "-"),
        ("album_ratio", "Distinct albums", "s", "--"),
        ("artist_ratio", "Distinct artists", "^", "-."),
    ]

    for column, label, marker, linestyle in metric_specs:
        axis.plot(
            x_positions,
            summary[column],
            marker=marker,
            linestyle=linestyle,
            linewidth=2,
            markersize=7,
            label=label,
        )

    axis.set_title("Content diversity within listening sessions")

    axis.set_xlabel("Scrobbles per session")

    axis.set_ylabel("Median distinct items / scrobbles")

    axis.set_ylim(0, 1.05)

    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    axis.set_xticks(x_positions)

    axis.set_xticklabels(
        [f"{row.size_bucket}\n(n={row.sessions:,})" for row in summary.itertuples(index=False)]
    )

    axis.grid(axis="y", alpha=0.25)

    axis.legend(title="Diversity level")

    figure.text(
        0.5,
        0.015,
        (
            "Sessions with one scrobble are excluded. "
            "Each line shows the median ratio of distinct "
            "tracks, albums or artists to total scrobbles "
            "within each session-size bucket."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.055, 1, 1))

    output_path = output_dir / "session_content_diversity_by_size.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_monthly_discovery(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    data = connection.execute(
        """
        SELECT
            month_start,
            scrobble_count,
            active_artists,
            new_artists,
            returning_artists,
            new_artist_scrobbles,
            cumulative_artists,
            discovery_rate_pct,
            new_artist_scrobble_share_pct

        FROM mart_monthly_discovery

        ORDER BY
            month_start
        """
    ).df()

    data["month_start"] = pd.to_datetime(data["month_start"])

    return data


def plot_monthly_artist_discovery(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    start_date: str | None = "2020-01-01",
    end_date: str | None = "2025-12-31",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data = load_monthly_discovery(connection)

    if start_date is not None:
        plot_data = data[data["month_start"] >= pd.Timestamp(start_date)].copy()
    else:
        plot_data = data.copy()

    if end_date is not None:
        plot_data = plot_data[plot_data["month_start"] <= pd.Timestamp(end_date)]

    all_months = pd.date_range(
        start=plot_data["month_start"].min(), end=plot_data["month_start"].max(), freq="MS"
    )

    monthly = (
        plot_data.set_index("month_start")
        .reindex(all_months)
        .rename_axis("month_start")
        .reset_index()
    )

    observed = monthly["scrobble_count"].notna()

    # The opening observed month is left-censored:
    # every artist necessarily appears as "new".
    opening_month = data["month_start"].min()

    discovery_rate = monthly["discovery_rate_pct"].copy()

    new_scrobble_share = monthly["new_artist_scrobble_share_pct"].copy()

    opening_mask = monthly["month_start"] == opening_month

    discovery_rate.loc[opening_mask] = float("nan")

    new_scrobble_share.loc[opening_mask] = float("nan")

    figure, (axis_counts, axis_rates) = plt.subplots(
        nrows=2, ncols=1, figsize=(15, 8), sharex=True, gridspec_kw={"height_ratios": [1.0, 1.15]}
    )

    axis_counts.bar(
        monthly["month_start"], monthly["returning_artists"], width=24, label="Returning artists"
    )

    axis_counts.bar(
        monthly["month_start"],
        monthly["new_artists"],
        bottom=monthly["returning_artists"],
        width=24,
        label="New artists",
    )

    axis_counts.set_title("Monthly artist activity")

    axis_counts.set_ylabel("Active artists")

    axis_counts.legend(loc="upper left")

    axis_counts.grid(axis="y", alpha=0.25)

    axis_counts.tick_params(axis="x", labelbottom=False)

    axis_rates.plot(
        monthly["month_start"],
        discovery_rate,
        marker="o",
        markersize=3,
        linewidth=1.5,
        label="New artists / active artists",
    )

    axis_rates.plot(
        monthly["month_start"],
        new_scrobble_share,
        marker="o",
        markersize=3,
        linewidth=1.5,
        label="Scrobbles on new artists",
    )

    axis_rates.set_title("Discovery intensity")

    axis_rates.set_ylabel("Share (%)")

    axis_rates.set_xlabel(None)

    axis_rates.set_ylim(0, 100)

    axis_rates.yaxis.set_major_formatter(PercentFormatter(xmax=100.0))

    axis_rates.legend(loc="upper right")

    axis_rates.grid(alpha=0.25)

    plot_start = monthly["month_start"].min()
    plot_end = monthly["month_start"].max()

    x_min = plot_start - pd.Timedelta(days=15)

    x_max = plot_end + pd.offsets.MonthEnd(1) + pd.Timedelta(days=15)

    halfyear_locator = mdates.MonthLocator(bymonth=(1, 7))

    halfyear_formatter = mdates.DateFormatter("%b/%Y")

    for axis in (axis_counts, axis_rates):
        axis.set_xlim(x_min, x_max)
        axis.margins(x=0)
        axis.xaxis.set_major_locator(halfyear_locator)
        axis.xaxis.set_major_formatter(halfyear_formatter)

    axis_counts.tick_params(axis="x", labelbottom=False)

    axis_rates.tick_params(axis="x", rotation=45)

    missing_months = monthly.loc[~observed, "month_start"]

    for month in missing_months:
        for axis in (axis_counts, axis_rates):
            axis.axvspan(
                month, month + pd.offsets.MonthBegin(1), alpha=0.04, color="black", linewidth=0
            )

    figure.suptitle("Artist discovery over time", y=0.995)

    figure.text(
        0.5,
        0.012,
        (
            "Grey shading indicates missing months within the observed series. "
            "Artist discovery status uses the full available history, including "
            "observations before this plotting window. "
            "Coverage begins in September 2019; 2026 is partial."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.04, 1, 0.97))

    output_path = output_dir / "monthly_artist_discovery.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def plot_cumulative_artist_discovery(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    start_date: str | None = "2019-01-01",
    end_date: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data = load_monthly_discovery(connection)

    plot_data = data.copy()

    if start_date is not None:
        plot_data = plot_data[plot_data["month_start"] >= pd.Timestamp(start_date)]

    if end_date is not None:
        plot_data = plot_data[plot_data["month_start"] <= pd.Timestamp(end_date)]

    plot_data = plot_data.copy()

    all_months = pd.date_range(
        start=plot_data["month_start"].min(), end=plot_data["month_start"].max(), freq="MS"
    )

    monthly = (
        plot_data.set_index("month_start")
        .reindex(all_months)
        .rename_axis("month_start")
        .reset_index()
    )

    figure, axis = plt.subplots(figsize=(14, 6))

    axis.step(monthly["month_start"], monthly["cumulative_artists"], where="post", linewidth=2)

    observed = monthly[monthly["cumulative_artists"].notna()].copy()

    year_end = (
        observed.assign(year=observed["month_start"].dt.year)
        .groupby("year", as_index=False)
        .tail(1)
    )

    axis.scatter(year_end["month_start"], year_end["cumulative_artists"], s=35, zorder=4)

    for row in year_end.itertuples(index=False):
        axis.annotate(
            f"{int(row.cumulative_artists):,}",
            (row.month_start, row.cumulative_artists),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )

    missing_months = monthly.loc[monthly["cumulative_artists"].isna(), "month_start"]

    for month in missing_months:
        axis.axvspan(
            month, month + pd.offsets.MonthBegin(1), alpha=0.05, color="black", linewidth=0
        )

    halfyear_locator = mdates.MonthLocator(bymonth=(1, 7))

    halfyear_formatter = mdates.DateFormatter("%b/%Y")

    axis.xaxis.set_major_locator(halfyear_locator)

    axis.xaxis.set_major_formatter(halfyear_formatter)

    axis.tick_params(axis="x", rotation=45)

    plot_start = monthly["month_start"].min()

    plot_end = monthly["month_start"].max()

    axis.set_xlim(
        plot_start - pd.Timedelta(days=15),
        plot_end + pd.offsets.MonthEnd(1) + pd.Timedelta(days=15),
    )

    axis.margins(x=0)

    axis.set_title("Cumulative artist discovery over time")

    axis.set_xlabel(None)

    axis.set_ylabel("Cumulative distinct artists")

    axis.grid(axis="y", alpha=0.25)

    figure.text(
        0.5,
        0.015,
        (
            "Cumulative counts include the full listening history, "
            "including artists first observed before the plotted window. "
            "Grey shading marks missing months in the displayed series."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.055, 1, 1))

    output_path = output_dir / "cumulative_artist_discovery.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(figure)

    return output_path


def load_artist_discovery_scatter_data(
    connection: duckdb.DuckDBPyConnection,
    *,
    start_date: str | None = "2019-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    data = load_monthly_discovery(connection)

    if start_date is not None:
        data = data[data["month_start"] >= pd.Timestamp(start_date)]

    if end_date is not None:
        data = data[data["month_start"] <= pd.Timestamp(end_date)]

    return data.copy()


def plot_artist_discovery_scatter(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_FIGURE_DIR,
    start_date: str | None = "2019-01-01",
    end_date: str | None = None,
    annotate_top_n: int = 8,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as connection:
        data = load_artist_discovery_scatter_data(
            connection, start_date=start_date, end_date=end_date
        )

    if data.empty:
        raise RuntimeError("No monthly discovery data available for the selected window.")

    data["month_start"] = pd.to_datetime(data["month_start"])
    data["year"] = data["month_start"].dt.year.astype(str)

    x = data["discovery_rate_pct"].astype(float)
    y = data["new_artist_scrobble_share_pct"].astype(float)

    x_median = float(x.median())
    y_median = float(y.median())

    # Score to pick standout months for annotation
    data["annotation_score"] = (x - x_median).abs() + (y - y_median).abs()

    points_to_annotate = (
        data.nlargest(annotate_top_n, "annotation_score").sort_values("month_start").copy()
    )

    figure, axis = plt.subplots(figsize=(10.5, 8.0))

    years = sorted(data["year"].unique())
    color_map = plt.get_cmap("tab10", len(years))

    for index, year in enumerate(years):
        year_data = data[data["year"] == year]

        axis.scatter(
            year_data["discovery_rate_pct"],
            year_data["new_artist_scrobble_share_pct"],
            s=55,
            alpha=0.85,
            label=year,
            color=color_map(index),
            edgecolors="white",
            linewidths=0.6,
        )

    # Median reference lines
    axis.axvline(x_median, linestyle="--", linewidth=1.2, color="dimgray", alpha=0.9)
    axis.axhline(y_median, linestyle="--", linewidth=1.2, color="dimgray", alpha=0.9)

    axis.text(x_median + 1.0, 2.0, f"Median x = {x_median:.1f}%", fontsize=9, color="dimgray")

    axis.text(1.0, y_median + 1.0, f"Median y = {y_median:.1f}%", fontsize=9, color="dimgray")

    for _, row in points_to_annotate.iterrows():
        label = row["month_start"].strftime("%b/%Y")

        axis.annotate(
            label,
            xy=(row["discovery_rate_pct"], row["new_artist_scrobble_share_pct"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )

    axis.set_title("Artist discovery: breadth vs intensity")
    axis.set_xlabel("New artists / active artists (%)")
    axis.set_ylabel("Scrobbles on new artists (%)")

    observed_max = max(float(x.max()), float(y.max()))

    axis_max = min(100.0, math.ceil(observed_max * 1.08 / 10.0) * 10.0)

    axis.set_xlim(0, axis_max)

    axis.set_ylim(0, axis_max)

    ticks = list(range(0, int(axis_max) + 1, 10))

    axis.set_xticks(ticks)
    axis.set_yticks(ticks)

    axis.xaxis.set_major_formatter(PercentFormatter(xmax=100.0))
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100.0))

    axis.grid(alpha=0.25)
    axis.legend(title="Year", loc="upper left", ncols=2)

    left_x = x_median * 0.45
    right_x = x_median + (axis_max - x_median) * 0.55

    lower_y = y_median * 0.45
    upper_y = y_median + (axis_max - y_median) * 0.55

    quadrant_style = {
        "ha": "center",
        "va": "center",
        "fontsize": 10,
        "color": "#666666",
        "alpha": 0.75,
    }

    axis.text(left_x, upper_y, "Narrow + deep\ndiscovery", **quadrant_style)

    axis.text(right_x, upper_y, "Broad + deep\ndiscovery", **quadrant_style)

    axis.text(left_x, lower_y, "Familiar\nlistening", **quadrant_style)

    axis.text(right_x, lower_y, "Broad + shallow\ndiscovery", **quadrant_style)

    figure.text(
        0.5,
        0.015,
        (
            "Each point represents one observed month. The x-axis measures the share "
            "of active artists newly observed that month; the y-axis measures the share "
            "of monthly scrobbles devoted to those artists.\n"
            "Newly observed status uses the full available listening history. "
            "Dashed lines mark medians within the plotted window; "
            "2026 includes January–August only."
        ),
        ha="center",
        fontsize=9,
    )

    figure.tight_layout(rect=(0, 0.05, 1, 1))

    output_path = output_dir / "artist_discovery_scatter.png"

    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)

    return output_path
