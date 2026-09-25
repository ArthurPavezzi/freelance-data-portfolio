import streamlit as st

st.set_page_config(page_title="Last.fm Analytics", page_icon="🎧", layout="wide")


pages = {
    "Analytics": [
        st.Page("pages/overview.py", title="Overview", icon=":material/home:", default=True),
        st.Page(
            "pages/artists_genres.py", title="Artists & Genres", icon=":material/library_music:"
        ),
        st.Page(
            "pages/listening_behavior.py", title="Listening Behavior", icon=":material/headphones:"
        ),
        # st.Page("pages/discovery.py", title="Discovery", icon=":material/explore:"),
    ]
}


navigation = st.navigation(pages)

navigation.run()
