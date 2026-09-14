import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class LastFMConfig:
    api_key: str
    username: str
    base_url: str = "https://ws.audioscrobbler.com/2.0/"
    user_agent: str = "freelance-data-portfolio/lastfm-analytics-platform"


def load_config() -> LastFMConfig:
    load_dotenv()

    api_key = os.getenv("LASTFM_API_KEY")
    username = os.getenv("LASTFM_USERNAME")

    missing = [
        name
        for name, value in {
            "LASTFM_API_KEY": api_key,
            "LASTFM_USERNAME": username,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    return LastFMConfig(
        api_key=api_key,
        username=username,
    )
