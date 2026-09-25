import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from common import load_parquet, make_color_map

artist_yearly = load_parquet("artist_yearly.parquet")
genre_yearly = load_parquet("genre_yearly.parquet")
genre_seasonality_yearly = load_parquet("genre_seasonality_yearly.parquet")
listening_by_decade_yearly = load_parquet("listening_by_decade_yearly.parquet")

st.title("Artists & Genres")

st.caption(
    "Explore how artist concentration, genre composition and "
    "seasonal listening patterns changed across the observed history."
)


# ---------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------

all_years = list(
    range(
        int(artist_yearly["listening_year"].min()), int(artist_yearly["listening_year"].max()) + 1
    )
)

default_start_year = 2020 if 2020 in all_years else all_years[0]

default_end_year = all_years[-1]


control_1, control_2, control_3 = st.columns([2, 1, 1])

with control_1:
    year_range = st.slider(
        "Year range",
        min_value=all_years[0],
        max_value=all_years[-1],
        value=(default_start_year, default_end_year),
    )

with control_2:
    top_n_artists = st.slider("Top artists", min_value=5, max_value=20, value=10, step=1)

with control_3:
    top_n_genres = st.slider("Top genres", min_value=5, max_value=20, value=10, step=1)


start_year, end_year = year_range


artist_window = artist_yearly[artist_yearly["listening_year"].between(start_year, end_year)].copy()

genre_window = genre_yearly[genre_yearly["listening_year"].between(start_year, end_year)].copy()


# ---------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------

st.divider()

st.subheader("Artists")


artist_ranking = (
    artist_window.groupby(["artist_id", "artist_name"], as_index=False)["scrobbles"]
    .sum()
    .sort_values("scrobbles", ascending=False)
    .head(top_n_artists)
)

artist_color_map = make_color_map(artist_ranking["artist_name"].tolist())


left_column, right_column = st.columns([1, 1.6])


with left_column:
    ranking_plot = artist_ranking.sort_values("scrobbles")

    artist_labels = ranking_plot["artist_name"].tolist()

    artist_ranking_figure = px.bar(
        ranking_plot,
        x="scrobbles",
        y="artist_name",
        orientation="h",
        title=f"Top {top_n_artists} artists, {start_year}–{end_year}",
        labels={"artist_name": "Artist", "scrobbles": "Scrobbles"},
    )

    artist_ranking_figure.update_yaxes(
        tickmode="array", tickvals=artist_labels, ticktext=artist_labels, automargin=True
    )

    artist_ranking_figure.update_layout(
        showlegend=False, height=max(450, 26 * len(artist_labels) + 140)
    )

    st.plotly_chart(artist_ranking_figure, width="stretch")


with right_column:
    selected_artist_ids = set(artist_ranking["artist_id"])

    artist_evolution = artist_window[artist_window["artist_id"].isin(selected_artist_ids)][
        ["artist_id", "artist_name", "listening_year", "scrobbles"]
    ].copy()

    observed_years = set(
        artist_yearly[artist_yearly["listening_year"].between(start_year, end_year)][
            "listening_year"
        ].unique()
    )

    artist_grid = pd.MultiIndex.from_product(
        [artist_ranking["artist_name"], range(start_year, end_year + 1)],
        names=["artist_name", "listening_year"],
    ).to_frame(index=False)

    artist_evolution = artist_grid.merge(
        artist_evolution[["artist_name", "listening_year", "scrobbles"]],
        on=["artist_name", "listening_year"],
        how="left",
    )

    observed_mask = artist_evolution["listening_year"].isin(observed_years)

    artist_evolution.loc[observed_mask, "scrobbles"] = artist_evolution.loc[
        observed_mask, "scrobbles"
    ].fillna(0)

    artist_evolution_figure = px.line(
        artist_evolution,
        x="listening_year",
        y="scrobbles",
        color="artist_name",
        markers=True,
        title="Artist listening through time",
        labels={"listening_year": "Year", "scrobbles": "Scrobbles", "artist_name": "Artist"},
        color_discrete_map=artist_color_map,
    )

    artist_evolution_figure.update_traces(connectgaps=False)

    artist_evolution_figure.update_xaxes(tickmode="linear", dtick=1)

    st.plotly_chart(artist_evolution_figure, width="stretch")


st.caption(
    "Artist rankings are recalculated within the selected window. "
    "Years with no observed listening data remain gaps rather than "
    "being interpreted as zero listening."
)


# ---------------------------------------------------------------------
# Genres
# ---------------------------------------------------------------------

st.divider()

st.subheader("Genres")


genre_ranking = (
    genre_window.groupby("canonical_genre", as_index=False)["weighted_scrobbles"]
    .sum()
    .sort_values("weighted_scrobbles", ascending=False)
    .head(top_n_genres)
)

selected_genres = list(genre_ranking["canonical_genre"])

genre_color_map = make_color_map(selected_genres, special_colors={"Other": "#9E9E9E"})

genre_composition = genre_window[genre_window["canonical_genre"].isin(selected_genres)][
    ["listening_year", "canonical_genre", "genre_share"]
].copy()

genre_composition["genre_share_pct"] = genre_composition["genre_share"] * 100


selected_share = (
    genre_composition.groupby("listening_year", as_index=False)["genre_share_pct"]
    .sum()
    .rename(columns={"genre_share_pct": "selected_share_pct"})
)

other_rows = selected_share.copy()

other_rows["canonical_genre"] = "Other"

other_rows["genre_share_pct"] = 100 - other_rows["selected_share_pct"]

other_rows = other_rows[["listening_year", "canonical_genre", "genre_share_pct"]]

genre_composition = pd.concat(
    [genre_composition[["listening_year", "canonical_genre", "genre_share_pct"]], other_rows],
    ignore_index=True,
)

genre_composition_figure = px.bar(
    genre_composition,
    x="listening_year",
    y="genre_share_pct",
    color="canonical_genre",
    title="Genre composition by year",
    labels={
        "listening_year": "Year",
        "genre_share_pct": "Share of genre-classified scrobbles (%)",
        "canonical_genre": "Genre",
    },
    category_orders={"canonical_genre": selected_genres + ["Other"]},
    color_discrete_map=genre_color_map,
)

genre_composition_figure.update_layout(barmode="stack")

genre_composition_figure.update_xaxes(tickmode="linear", dtick=1)

genre_composition_figure.update_yaxes(range=[0, 100])

st.plotly_chart(genre_composition_figure, width="stretch")

st.caption(
    "Genre shares use genre-classified scrobbles as the denominator. "
    "The top genres are selected across the current year window; "
    "all remaining genres are grouped as Other."
)

# ---------------------------------------------------------------------
# Music by decade
# ---------------------------------------------------------------------

st.divider()

st.subheader("Music by decade")


decade_yearly_window = listening_by_decade_yearly[
    listening_by_decade_yearly["listening_year"].between(start_year, end_year)
].copy()


if not decade_yearly_window.empty:
    decade_order = [
        f"{int(decade)}s"
        for decade in sorted(decade_yearly_window["release_decade"].drop_duplicates().tolist())
    ]

    decade_color_map = make_color_map(decade_order)

    year_coverage = (
        decade_yearly_window[
            [
                "listening_year",
                "year_total_scrobbles",
                "year_release_year_covered_scrobbles",
                "year_release_year_unknown_scrobbles",
                "year_scrobbles_without_album",
                "release_year_dataset_coverage",
                "months_observed",
                "is_full_calendar_year",
            ]
        ]
        .drop_duplicates()
        .sort_values("listening_year")
    )

    window_total_scrobbles = int(year_coverage["year_total_scrobbles"].sum())

    window_resolved_scrobbles = int(year_coverage["year_release_year_covered_scrobbles"].sum())

    window_unresolved_scrobbles = window_total_scrobbles - window_resolved_scrobbles

    window_coverage_pct = 100 * window_resolved_scrobbles / window_total_scrobbles

    metric_1, metric_2, metric_3 = st.columns(3)

    metric_1.metric("Release-date coverage", f"{window_coverage_pct:.1f}%")

    metric_2.metric("Resolved scrobbles", f"{window_resolved_scrobbles:,}")

    metric_3.metric("Unresolved release date", f"{window_unresolved_scrobbles:,}")

    # -------------------------------------------------------------
    # Overall decade distribution within selected listening years
    # -------------------------------------------------------------

    decade_summary = (
        decade_yearly_window.groupby(["release_decade", "release_decade_label"], as_index=False)[
            "scrobble_count"
        ]
        .sum()
        .sort_values("release_decade")
    )

    decade_summary["resolved_share_pct"] = (
        100 * decade_summary["scrobble_count"] / decade_summary["scrobble_count"].sum()
    )

    decade_figure = px.bar(
        decade_summary,
        x="release_decade_label",
        y="resolved_share_pct",
        color="release_decade_label",
        title=f"Listening by release decade, {start_year}–{end_year}",
        labels={
            "release_decade_label": "Release decade",
            "resolved_share_pct": "Share of release-dated scrobbles (%)",
        },
        category_orders={"release_decade_label": decade_order},
        color_discrete_map=decade_color_map,
        custom_data=["scrobble_count"],
    )

    decade_figure.update_traces(
        hovertemplate=(
            "Decade: %{x}<br>Share: %{y:.2f}%<br>Scrobbles: %{customdata[0]:,.0f}<extra></extra>"
        )
    )

    decade_figure.update_layout(showlegend=False)
    decade_figure.update_yaxes(rangemode="tozero")

    st.plotly_chart(decade_figure, width="stretch")

    st.caption(
        "Shares are calculated only among scrobbles with a resolved "
        "release year. Release-date coverage for the selected listening "
        f"window is {window_coverage_pct:.1f}% of all observed scrobbles."
    )

    # -------------------------------------------------------------
    # Decade composition by listening year
    # -------------------------------------------------------------

    decade_evolution = decade_yearly_window.copy()
    decade_evolution["resolved_share_pct"] = (
        100 * decade_evolution["decade_share_within_resolved_year"]
    )
    decade_evolution["coverage_pct"] = 100 * decade_evolution["release_year_dataset_coverage"]

    decade_evolution_figure = px.bar(
        decade_evolution,
        x="listening_year",
        y="resolved_share_pct",
        color="release_decade_label",
        title="Release-decade mix by listening year",
        labels={
            "listening_year": "Listening year",
            "resolved_share_pct": "Share of release-dated scrobbles (%)",
            "release_decade_label": "Release decade",
        },
        category_orders={"release_decade_label": decade_order},
        color_discrete_map=(decade_color_map),
        custom_data=[
            "scrobble_count",
            "distinct_tracks",
            "distinct_artists",
            "coverage_pct",
            "months_observed",
            "is_full_calendar_year",
        ],
    )

    decade_evolution_figure.update_traces(
        hovertemplate=(
            "Listening year: %{x}"
            "<br>Release decade: "
            "%{fullData.name}"
            "<br>Share: %{y:.2f}%"
            "<br>Scrobbles: "
            "%{customdata[0]:,.0f}"
            "<br>Distinct tracks: "
            "%{customdata[1]:,.0f}"
            "<br>Distinct artists: "
            "%{customdata[2]:,.0f}"
            "<br>Release-date coverage: "
            "%{customdata[3]:.1f}%"
            "<br>Months observed: "
            "%{customdata[4]}"
            "<extra></extra>"
        )
    )

    decade_evolution_figure.update_layout(barmode="stack")
    decade_evolution_figure.update_xaxes(tickmode="linear", dtick=1)
    decade_evolution_figure.update_yaxes(range=[0, 100])

    st.plotly_chart(decade_evolution_figure, width="stretch")

    partial_years = (
        year_coverage.loc[~year_coverage["is_full_calendar_year"], "listening_year"]
        .astype(int)
        .tolist()
    )

    if partial_years:
        partial_year_text = ", ".join(str(year) for year in partial_years)

        st.caption(
            "Each bar sums to 100% of the scrobbles with a resolved "
            "release year in that listening year. "
            f"Partial calendar years in the selected window: "
            f"{partial_year_text}."
        )

    else:
        st.caption(
            "Each bar sums to 100% of the scrobbles with a resolved release year in that listening year."
        )

    # -------------------------------------------------------------
    # Release-date coverage by listening year
    # -------------------------------------------------------------

    year_coverage = year_coverage.copy()

    year_coverage["coverage_pct"] = 100 * year_coverage["release_year_dataset_coverage"]

    year_coverage["coverage_status"] = year_coverage["is_full_calendar_year"].map(
        {True: "Full calendar year", False: "Partial calendar year"}
    )

    coverage_figure = px.bar(
        year_coverage,
        x="listening_year",
        y="coverage_pct",
        title="Release-date coverage by listening year",
        labels={"listening_year": "Listening year", "coverage_pct": "Release-date coverage (%)"},
        custom_data=[
            "year_release_year_covered_scrobbles",
            "year_total_scrobbles",
            "months_observed",
            "coverage_status",
        ],
        text="coverage_pct",
    )

    coverage_figure.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "Listening year: %{x}"
            "<br>Coverage: %{y:.2f}%"
            "<br>Resolved scrobbles: "
            "%{customdata[0]:,.0f}"
            "<br>Total scrobbles: "
            "%{customdata[1]:,.0f}"
            "<br>Months observed: "
            "%{customdata[2]}"
            "<br>%{customdata[3]}"
            "<extra></extra>"
        ),
    )

    coverage_figure.update_xaxes(tickmode="linear", dtick=1)
    coverage_figure.update_yaxes(range=[0, 100])
    coverage_figure.update_layout(showlegend=False)

    st.plotly_chart(coverage_figure, width="stretch")

    st.caption(
        "Coverage is shown separately because the share of scrobbles "
        "with a resolved release year varies across listening years. "
        "Missing release dates are not treated as a decade."
    )

else:
    st.info("No release-decade data are available for the selected year range.")

# ---------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------

st.divider()

st.subheader("Genre seasonality")


full_season_years = sorted(
    genre_seasonality_yearly.loc[genre_seasonality_yearly["is_full_season_year"], "season_year"]
    .drop_duplicates()
    .astype(int)
    .tolist()
)


if full_season_years:
    seasonality_year = st.selectbox(
        "Season year", options=full_season_years, index=len(full_season_years) - 1
    )

    year_mask = genre_seasonality_yearly["season_year"] == seasonality_year

    rank_mask = genre_seasonality_yearly["genre_rank_in_season_year"] <= top_n_genres

    support_mask = genre_seasonality_yearly["season_year_genre_weighted_scrobbles"] >= 25

    seasonality = genre_seasonality_yearly.loc[year_mask & rank_mask & support_mask].copy()

    genre_order = (
        seasonality[["canonical_genre", "genre_rank_in_season_year"]]
        .drop_duplicates()
        .sort_values("genre_rank_in_season_year")["canonical_genre"]
        .tolist()
    )

    season_order = ["Summer", "Autumn", "Winter", "Spring"]

    heatmap = seasonality.pivot(
        index="canonical_genre", columns="season_name", values="seasonality_index_season_year"
    ).reindex(index=genre_order, columns=season_order)

    heatmap_text = [
        ["" if pd.isna(value) else f"{value:.2f}" for value in row] for row in heatmap.to_numpy()
    ]

    missing_mask = heatmap.isna().astype(int)

    seasonality_figure = go.Figure()

    seasonality_figure.add_trace(
        go.Heatmap(
            z=missing_mask.values,
            x=heatmap.columns,
            y=heatmap.index,
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "#BDBDBD"]],
            zmin=0,
            zmax=1,
            showscale=False,
            hoverinfo="skip",
        )
    )

    seasonality_figure.add_trace(
        go.Heatmap(
            z=heatmap.values,
            x=heatmap.columns,
            y=heatmap.index,
            zmin=0.5,
            zmax=1.5,
            zmid=1.0,
            colorscale="RdBu_r",
            colorbar={"title": "Seasonality<br>index"},
            text=heatmap_text,
            texttemplate="%{text}",
            hoverongaps=False,
            hovertemplate=("Genre: %{y}<br>Season: %{x}<br>Index: %{z:.2f}<extra></extra>"),
        )
    )

    seasonality_figure.update_layout(
        title=f"Southern Hemisphere genre seasonality, season year {seasonality_year}",
        xaxis_title="Southern Hemisphere season",
        yaxis_title="Genre",
    )

    seasonality_figure.update_yaxes(
        tickmode="array", tickvals=genre_order, ticktext=genre_order, automargin=True
    )

    seasonality_figure.update_layout(height=max(450, 28 * len(genre_order) + 180))

    st.plotly_chart(seasonality_figure, width="stretch")

    st.caption(
        "A seasonality index of 1 indicates the genre's season-year baseline. "
        "Values above 1 indicate relative seasonal concentration; values below 1 "
        "indicate relative underrepresentation. Season years run from December "
        "of the previous calendar year through November of the labeled year. "
        "Only complete season years are shown, and genre-years with fewer than "
        "25 weighted scrobbles are excluded."
    )
else:
    st.info("No full years are available for the seasonality view.")
