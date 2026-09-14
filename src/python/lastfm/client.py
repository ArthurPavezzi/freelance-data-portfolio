import time
from typing import Any, Self

import httpx

from lastfm.config import LastFMConfig

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


class LastFMClient:
    def __init__(
        self,
        config: LastFMConfig,
        *,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

        self.client = httpx.Client(
            base_url=config.base_url,
            headers={
                "User-Agent": config.user_agent,
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _sleep_before_retry(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> None:
        retry_after = None

        if response is not None:
            retry_after = response.headers.get("Retry-After")

        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self.backoff_seconds * 2**attempt
        else:
            delay = self.backoff_seconds * 2**attempt

        time.sleep(delay)

    def get_recent_tracks(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "method": "user.getrecenttracks",
            "user": self.config.username,
            "api_key": self.config.api_key,
            "format": "json",
            "page": page,
            "limit": limit,
        }

        if from_timestamp is not None:
            params["from"] = from_timestamp

        if to_timestamp is not None:
            params["to"] = to_timestamp

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(
                    "",
                    params=params,
                )
            except httpx.RequestError:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "Last.fm request failed after "
                        f"{self.max_retries + 1} attempts "
                        f"on page {page}"
                    ) from None

                self._sleep_before_retry(attempt)
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "Last.fm API returned "
                        f"HTTP {response.status_code} "
                        f"after {self.max_retries + 1} attempts "
                        f"on page {page}"
                    ) from None

                self._sleep_before_retry(
                    attempt,
                    response,
                )
                continue

            if response.is_error:
                raise RuntimeError(
                    f"Last.fm API returned HTTP {response.status_code} on page {page}"
                ) from None

            payload = response.json()

            if "error" in payload:
                api_error = int(payload["error"])

                # Last.fm error 29:
                # rate limit exceeded
                if api_error == 29 and attempt < self.max_retries:
                    self._sleep_before_retry(
                        attempt,
                        response,
                    )
                    continue

                raise RuntimeError(
                    f"Last.fm API error {api_error}: {payload.get('message', 'Unknown error')}"
                )

            return payload

        raise RuntimeError("Unexpected Last.fm retry state")
