import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from common import load_parquet
from plotly.subplots import make_subplots

hourly = load_parquet("listening_by_hour.parquet")
sessions = load_parquet("listening_sessions.parquet")


st.title("Listening Behavior")

st.caption(
    "Explore daily listening rhythms, session structure "
    "and how listening diversity changes as sessions become longer."
)


# ---------------------------------------------------------------------
# Daily rhythm
# ---------------------------------------------------------------------

st.divider()

st.subheader("Daily rhythm")


overall_hourly = (
    hourly.groupby("listening_hour", as_index=False)["scrobble_count"]
    .sum()
    .sort_values("listening_hour")
)

overall_hourly["scrobble_share_pct"] = (
    overall_hourly["scrobble_count"] / overall_hourly["scrobble_count"].sum() * 100
)

hourly_temporal = load_parquet("listening_by_hour_temporal.parquet")


hourly["day_type"] = hourly["weekday_iso"].map(lambda value: "Weekday" if value <= 5 else "Weekend")

day_type_hourly = hourly.groupby(["day_type", "listening_hour"], as_index=False)[
    "scrobble_count"
].sum()

day_type_hourly["share_pct"] = (
    day_type_hourly["scrobble_count"]
    / day_type_hourly.groupby("day_type")["scrobble_count"].transform("sum")
    * 100
)


left_column, right_column = st.columns(2)


with left_column:
    overall_hourly_figure = px.bar(
        overall_hourly,
        x="listening_hour",
        y="scrobble_share_pct",
        title="Listening by hour",
        labels={"listening_hour": "Local hour", "scrobble_share_pct": "Share of scrobbles (%)"},
    )

    overall_hourly_figure.update_xaxes(tickmode="linear", tick0=0, dtick=2)

    overall_hourly_figure.update_layout(showlegend=False)

    st.plotly_chart(overall_hourly_figure, width="stretch")


with right_column:
    day_type_figure = px.line(
        day_type_hourly,
        x="listening_hour",
        y="share_pct",
        color="day_type",
        markers=True,
        title="Weekday vs weekend rhythm",
        labels={
            "listening_hour": "Local hour",
            "share_pct": "Share within day type (%)",
            "day_type": "Day type",
        },
    )

    day_type_figure.update_xaxes(tickmode="linear", tick0=0, dtick=2)

    st.plotly_chart(day_type_figure, width="stretch")


weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

weekday_heatmap = hourly.pivot(
    index="weekday_name", columns="listening_hour", values="avg_scrobbles_per_active_day"
).reindex(weekday_order)


weekday_heatmap_figure = px.imshow(
    weekday_heatmap,
    aspect="auto",
    text_auto=".1f",
    title="Listening intensity by weekday and hour",
    labels={"x": "Local hour", "y": "Weekday", "color": "Avg. scrobbles per active day"},
)

weekday_heatmap_figure.update_xaxes(tickmode="linear", tick0=0, dtick=1)

st.plotly_chart(weekday_heatmap_figure, width="stretch")

st.caption(
    "Hourly profiles use the full observed history. "
    "The weekday heatmap normalizes by active days, "
    "reducing differences caused simply by unequal weekday coverage."
)


# ---------------------------------------------------------------------
# Session window
# ---------------------------------------------------------------------

st.divider()

st.subheader("Session structure")


sessions["month_start"] = pd.to_datetime(sessions["month_start"])

session_years = sorted(sessions["month_start"].dt.year.unique())

default_start_year = 2020 if 2020 in session_years else session_years[0]

session_year_range = st.slider(
    "Session year range",
    min_value=int(session_years[0]),
    max_value=int(session_years[-1]),
    value=(int(default_start_year), int(session_years[-1])),
)

session_start_year, session_end_year = session_year_range

session_window = sessions[
    sessions["month_start"].dt.year.between(session_start_year, session_end_year)
].copy()


# ---------------------------------------------------------------------
# Session KPIs
# ---------------------------------------------------------------------

metric_columns = st.columns(5)

metric_columns[0].metric("Sessions", f"{len(session_window):,}")

metric_columns[1].metric("Median scrobbles", f"{session_window['scrobble_count'].median():.0f}")

metric_columns[2].metric(
    "Median span", f"{session_window['session_span_minutes'].median():.1f} min"
)

metric_columns[3].metric("Median artists", f"{session_window['distinct_artists'].median():.0f}")

metric_columns[4].metric("Median tracks", f"{session_window['distinct_tracks'].median():.0f}")


# ---------------------------------------------------------------------
# Distribution buckets
# ---------------------------------------------------------------------

size_labels = ["1", "2–3", "4–5", "6–10", "11–20", "21–40", "41–80", "81+"]

session_window["size_bucket"] = pd.cut(
    session_window["scrobble_count"],
    bins=[0, 1, 3, 5, 10, 20, 40, 80, float("inf")],
    labels=size_labels,
)


span_labels = ["0", "1–5", "6–15", "16–30", "31–60", "61–120", "121–240", "241+"]

session_window["span_bucket"] = pd.cut(
    session_window["session_span_minutes"],
    bins=[-0.001, 0, 5, 15, 30, 60, 120, 240, float("inf")],
    labels=span_labels,
)


size_distribution = (
    session_window["size_bucket"]
    .value_counts(sort=False)
    .reindex(size_labels, fill_value=0)
    .rename_axis("bucket")
    .reset_index(name="sessions")
)

size_distribution["share_pct"] = (
    size_distribution["sessions"] / size_distribution["sessions"].sum() * 100
)


span_distribution = (
    session_window["span_bucket"]
    .value_counts(sort=False)
    .reindex(span_labels, fill_value=0)
    .rename_axis("bucket")
    .reset_index(name="sessions")
)

span_distribution["share_pct"] = (
    span_distribution["sessions"] / span_distribution["sessions"].sum() * 100
)


left_column, right_column = st.columns(2)


with left_column:
    size_figure = px.bar(
        size_distribution,
        x="bucket",
        y="share_pct",
        title="Session size distribution",
        labels={"bucket": "Scrobbles per session", "share_pct": "Sessions (%)"},
    )

    size_figure.update_layout(showlegend=False)

    st.plotly_chart(size_figure, width="stretch")


with right_column:
    span_figure = px.bar(
        span_distribution,
        x="bucket",
        y="share_pct",
        title="Session span distribution",
        labels={"bucket": "Session span (minutes)", "share_pct": "Sessions (%)"},
    )

    span_figure.update_layout(showlegend=False)

    st.plotly_chart(span_figure, width="stretch")


# ---------------------------------------------------------------------
# Size vs span
# ---------------------------------------------------------------------

positive_sessions = session_window[session_window["session_span_minutes"] >= 0].copy()

positive_sessions["span_for_log"] = positive_sessions["session_span_minutes"] + 1


size_span_figure = px.scatter(
    positive_sessions,
    x="scrobble_count",
    y="span_for_log",
    opacity=0.35,
    title="Session size vs span",
    labels={"scrobble_count": "Scrobbles per session", "span_for_log": "Session span (minutes)"},
    hover_data={
        "session_span_minutes": ":.2f",
        "distinct_artists": True,
        "distinct_tracks": True,
        "distinct_albums": True,
        "span_for_log": False,
    },
)

size_span_figure.update_xaxes(type="log")

size_span_figure.update_yaxes(type="log")

session_size_ticks = [1, 2, 5, 10, 20, 50, 100]

session_span_ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500]


size_span_figure.update_xaxes(
    type="log",
    tickmode="array",
    tickvals=session_size_ticks,
    ticktext=[str(value) for value in session_size_ticks],
)

size_span_figure.update_yaxes(
    type="log",
    tickmode="array",
    tickvals=session_span_ticks,
    ticktext=[str(value) for value in session_span_ticks],
)

st.plotly_chart(size_span_figure, width="stretch")

st.caption(
    "Both axes are logarithmic. One minute is added to session span "
    "only for plotting so that zero-span sessions remain visible."
)


# ---------------------------------------------------------------------
# Diversity
# ---------------------------------------------------------------------

st.divider()

st.subheader("Session diversity")


multi_scrobble_sessions = session_window[session_window["scrobble_count"] > 1].copy()

multi_scrobble_sessions["artist_ratio"] = (
    multi_scrobble_sessions["distinct_artists"] / multi_scrobble_sessions["scrobble_count"]
)

multi_scrobble_sessions["track_ratio"] = (
    multi_scrobble_sessions["distinct_tracks"] / multi_scrobble_sessions["scrobble_count"]
)

multi_scrobble_sessions["album_ratio"] = (
    multi_scrobble_sessions["distinct_albums"] / multi_scrobble_sessions["scrobble_count"]
)


diversity = (
    multi_scrobble_sessions.groupby("size_bucket", observed=True)
    .agg(
        artist_ratio=("artist_ratio", "median"),
        track_ratio=("track_ratio", "median"),
        album_ratio=("album_ratio", "median"),
        sessions=("scrobble_count", "size"),
    )
    .reset_index()
)


diversity_long = diversity.melt(
    id_vars=["size_bucket", "sessions"],
    value_vars=["artist_ratio", "album_ratio", "track_ratio"],
    var_name="dimension",
    value_name="median_ratio",
)

diversity_long["dimension"] = diversity_long["dimension"].map(
    {"artist_ratio": "Artists", "album_ratio": "Albums", "track_ratio": "Tracks"}
)

diversity_long["median_ratio_pct"] = diversity_long["median_ratio"] * 100


diversity_figure = px.line(
    diversity_long,
    x="size_bucket",
    y="median_ratio_pct",
    color="dimension",
    markers=True,
    title="Content diversity by session size",
    labels={
        "size_bucket": "Scrobbles per session",
        "median_ratio_pct": "Median distinct items / scrobbles (%)",
        "dimension": "Distinct",
    },
)

diversity_figure.update_yaxes(range=[0, 105])

st.plotly_chart(diversity_figure, width="stretch")

st.caption(
    "Single-scrobble sessions are excluded from the diversity panel. "
    "A ratio of 100% means every scrobble in the session belongs to "
    "a distinct artist, album or track."
)

# ---------------------------------------------------------------------
# Listening clock by year
# ---------------------------------------------------------------------

YEAR_COLORS = {
    2020: "#1f77b4",
    2021: "#ff7f0e",
    2022: "#2ca02c",
    2023: "#d62728",
    2024: "#9467bd",
    2025: "#8c564b",
    2026: "#17becf",
}

available_clock_years = sorted(
    hourly_temporal.loc[hourly_temporal["listening_year"] >= 2020, "listening_year"]
    .drop_duplicates()
    .astype(int)
    .tolist()
)

selected_clock_years = st.multiselect(
    "Years shown", options=available_clock_years, default=available_clock_years
)

if not selected_clock_years:
    st.warning("Select at least one year to display the listening clock.")
    st.stop()

hourly_by_year = (
    hourly_temporal[hourly_temporal["listening_year"].isin(selected_clock_years)]
    .groupby(["listening_year", "listening_hour"], as_index=False)["scrobble_count"]
    .sum()
)

hourly_by_year["year_total_scrobbles"] = hourly_by_year.groupby("listening_year")[
    "scrobble_count"
].transform("sum")

hourly_by_year["share_within_year_pct"] = (
    100 * hourly_by_year["scrobble_count"] / hourly_by_year["year_total_scrobbles"]
)

hourly_by_year["year_label"] = hourly_by_year["listening_year"].astype(int).astype(str)

mean_clock = (
    hourly_by_year.groupby("listening_hour", as_index=False)["share_within_year_pct"]
    .mean()
    .rename(columns={"share_within_year_pct": "mean_share_pct"})
)

clock_figure = px.line(
    hourly_by_year,
    x="listening_hour",
    y="share_within_year_pct",
    color="year_label",
    markers=True,
    title="Listening clock by year",
    labels={
        "listening_hour": "Local hour",
        "share_within_year_pct": "Share of yearly scrobbles (%)",
        "color": "Year",
    },
)

clock_figure.update_xaxes(tickmode="linear", tick0=0, dtick=1, range=[0, 23])

clock_figure.update_layout(legend_title_text="Year")

st.plotly_chart(clock_figure, width="stretch")

st.caption(
    "Each yearly profile is normalized to that year's observed scrobbles, "
    "so the chart compares the shape of the listening day rather than "
    "annual listening volume. 2020–2025 have complete calendar-year "
    "coverage. 2026 is partial: August is unobserved and September is "
    "only partially observed."
)

polar_columns = 4

polar_rows = math.ceil(len(selected_clock_years) / polar_columns)

polar_specs = [[{"type": "polar"} for _ in range(polar_columns)] for _ in range(polar_rows)]

polar_titles = [str(year) for year in selected_clock_years]
polar_titles.extend([""] * (polar_rows * polar_columns - len(polar_titles)))

polar_figure = make_subplots(
    rows=polar_rows,
    cols=polar_columns,
    specs=polar_specs,
    subplot_titles=polar_titles,
    horizontal_spacing=0.06,
    vertical_spacing=0.12,
)

hour_labels = [f"{hour:02d}:00" for hour in range(24)]

reference_theta = (mean_clock["listening_hour"].astype(float) * 15).tolist()
reference_r = mean_clock["mean_share_pct"].tolist()
reference_customdata = hour_labels.copy()

reference_theta_closed = reference_theta + [reference_theta[0]]
reference_r_closed = reference_r + [reference_r[0]]
reference_customdata_closed = reference_customdata + [reference_customdata[0]]

for index, year in enumerate(selected_clock_years):
    row = index // polar_columns + 1
    column = index % polar_columns + 1

    year_frame = hourly_by_year[hourly_by_year["listening_year"] == year].sort_values(
        "listening_hour"
    )

    theta = (year_frame["listening_hour"].astype(float) * 15).tolist()
    radius = year_frame["share_within_year_pct"].tolist()
    customdata = [f"{hour:02d}:00" for hour in year_frame["listening_hour"].astype(int).tolist()]

    polar_figure.add_trace(
        go.Barpolar(
            theta=theta,
            r=radius,
            width=[12] * len(theta),
            marker_color=YEAR_COLORS[year],
            marker_line_color=YEAR_COLORS[year],
            marker_line_width=0.5,
            opacity=0.75,
            name=str(year),
            showlegend=False,
            customdata=customdata,
            hovertemplate=(f"{year}<br>Hour: %{{customdata}}<br>Share: %{{r:.2f}}%<extra></extra>"),
        ),
        row=row,
        col=column,
    )

    polar_figure.add_trace(
        go.Scatterpolar(
            theta=reference_theta_closed,
            r=reference_r_closed,
            mode="lines",
            line={"color": "#6e6e6e", "width": 2, "dash": "dash"},
            name="Mean yearly profile",
            showlegend=index == 0,
            customdata=reference_customdata_closed,
            hovertemplate=(
                "Mean yearly profile<br>Hour: %{customdata}<br>Share: %{r:.2f}%<extra></extra>"
            ),
        ),
        row=row,
        col=column,
    )

radial_max = max(
    float(hourly_by_year["share_within_year_pct"].max()), float(mean_clock["mean_share_pct"].max())
)

radial_max = math.ceil(radial_max * 1.10)

angular_axis = {
    "tickmode": "array",
    "tickvals": [0, 45, 90, 135, 180, 225, 270, 315],
    "ticktext": ["00", "03", "06", "09", "12", "15", "18", "21"],
    "direction": "clockwise",
    "rotation": 90,
}

radial_axis = {"range": [0, radial_max], "ticksuffix": "%"}

for polar_index in range(1, len(selected_clock_years) + 1):
    suffix = "" if polar_index == 1 else str(polar_index)

    polar_figure.update_layout(
        {f"polar{suffix}": {"angularaxis": angular_axis, "radialaxis": radial_axis}}
    )

polar_figure.update_layout(
    title="Annual listening clocks",
    height=370 * polar_rows,
    margin={"t": 90, "b": 40},
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
)

st.plotly_chart(polar_figure, width="stretch")

st.caption(
    "Each polar panel shows the hourly distribution of observed "
    "scrobbles within one calendar year. Bars show the selected year's "
    "profile, while the dashed grey line shows the equal-weight mean of "
    "the normalized yearly profiles currently selected above. All panels "
    "use the same radial scale. 2026 is partial: August is unobserved "
    "and September is only partially observed."
)
