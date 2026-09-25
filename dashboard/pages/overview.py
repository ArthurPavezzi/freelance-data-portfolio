import plotly.express as px
import streamlit as st
from common import load_parquet

overview = load_parquet("overview.parquet")

artist_yearly = load_parquet("artist_yearly.parquet")

artist_lifecycle = load_parquet("artist_lifecycle.parquet")

hourly = load_parquet("listening_by_hour.parquet")


summary = overview.iloc[0]


st.title("Last.fm Analytics")

st.caption(
    "A reproducible listening-data pipeline built from "
    "Last.fm API snapshots, DuckDB, SQL transformations "
    "and public analytical exports."
)

metric_columns = st.columns(5)

metric_columns[0].metric("Scrobbles", f"{int(summary['scrobbles']):,}")

metric_columns[1].metric("Artists", f"{int(summary['artists']):,}")

metric_columns[2].metric("Tracks", f"{int(summary['tracks']):,}")

metric_columns[3].metric("Albums", f"{int(summary['albums']):,}")

metric_columns[4].metric("Sessions", f"{int(summary['sessions']):,}")


st.divider()


yearly = (
    artist_yearly.groupby("listening_year", as_index=False)["scrobbles"]
    .sum()
    .sort_values("listening_year")
)

yearly_figure = px.bar(
    yearly,
    x="listening_year",
    y="scrobbles",
    title="Observed listening by year",
    labels={"listening_year": "Year", "scrobbles": "Scrobbles"},
)

yearly_figure.update_layout(showlegend=False)

st.plotly_chart(yearly_figure, width="stretch")

st.caption(
    "Historical coverage is incomplete before 2020; 2017–2018 contain no observed listening data."
)


left_column, right_column = st.columns(2)


with left_column:
    top_artists = (
        artist_lifecycle[["artist_name", "total_scrobbles"]]
        .sort_values("total_scrobbles", ascending=False)
        .head(15)
        .sort_values("total_scrobbles", ascending=True)
    )

    artist_figure = px.bar(
        top_artists,
        x="total_scrobbles",
        y="artist_name",
        orientation="h",
        title="Top artists",
        labels={"artist_name": "Artist", "total_scrobbles": "Scrobbles"},
    )

    artist_figure.update_layout(showlegend=False)

    st.plotly_chart(artist_figure, width="stretch")


with right_column:
    hourly_figure = px.bar(
        hourly,
        x="listening_hour",
        y="scrobble_count",
        title="Listening by hour",
        labels={"listening_hour": "Local hour", "scrobble_count": "Scrobbles"},
    )

    hourly_figure.update_xaxes(tickmode="linear", tick0=0, dtick=2)

    hourly_figure.update_layout(showlegend=False)

    st.plotly_chart(hourly_figure, width="stretch")


st.divider()


first_observed = summary["first_observed_at"]

last_observed = summary["last_observed_at"]

st.caption(
    "Observed period: "
    f"{first_observed:%d %b %Y} – "
    f"{last_observed:%d %b %Y}. "
    "Dashboard data are served from public analytical "
    "Parquet exports rather than raw listening snapshots."
)
