from pathlib import Path

import duckdb
import streamlit as st
from plotly.colors import qualitative

PUBLIC_DIR = Path("data/processed/lastfm/public")

CATEGORY_PALETTE = qualitative.Dark24
OTHER_COLOR = "#9E9E9E"


def make_color_map(categories, *, special_colors=None):
    categories = list(dict.fromkeys(categories))

    if len(categories) > len(CATEGORY_PALETTE):
        raise ValueError(
            f"Too many categories for the dashboard palette: {len(categories)} > {len(CATEGORY_PALETTE)}"
        )

    color_map = {category: CATEGORY_PALETTE[index] for index, category in enumerate(categories)}

    if special_colors is not None:
        color_map.update(special_colors)

    return color_map


@st.cache_data
def load_parquet(filename: str):
    path = PUBLIC_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Dashboard export not found: {path}")

    with duckdb.connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM read_parquet(?)
            """,
            [str(path)],
        ).df()
