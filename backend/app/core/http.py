"""Polite HTTP client shared by all connectors.

- Identifying User-Agent, timeouts, redirects followed.
- Minimum delay between requests to the same host.
- Retries with exponential backoff, only for transient failures (timeouts, connection errors,
  HTTP 429 and 5xx). HTTP 403 and other 4xx are never retried: they usually mean access is
  denied, and retrying would amount to working around it.
- Conditional GET (ETag / Last-Modified) so unchanged feeds are not downloaded again.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.core.logging import log_event

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_S = 300.0


class FetchError(Exception):
    def __init__(self, message: str, status_code: int | None = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


@dataclass
class FetchResponse:
    url: str
    status_code: int
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)
    attempts: int = 1

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304


class PoliteHttpClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.http_timeout_s,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _wait_for_host(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.settings.per_host_delay_s - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _backoff(self, attempt: int) -> float:
        return self.settings.http_backoff_base_s * (2 ** (attempt - 1))

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if value and value.strip().isdigit():
            return min(float(value), MAX_RETRY_AFTER_S)
        return None

    def get(self, url: str, etag: str | None = None, last_modified: str | None = None) -> FetchResponse:
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        max_attempts = self.settings.http_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            self._wait_for_host(url)
            try:
                response = self._client.get(url, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == max_attempts:
                    raise FetchError(f"{type(exc).__name__}: {exc}", None, attempt) from exc
                delay = self._backoff(attempt)
                log_event(logger, "http_retry", logging.WARNING, url=url, attempt=attempt,
                          reason=type(exc).__name__, delay_s=delay)
                self._sleep(delay)
                continue

            status = response.status_code
            if status in RETRYABLE_STATUS and attempt < max_attempts:
                delay = self._retry_after(response) or self._backoff(attempt)
                log_event(logger, "http_retry", logging.WARNING, url=url, attempt=attempt,
                          reason=f"HTTP {status}", delay_s=delay)
                self._sleep(delay)
                continue
            if status >= 400:
                raise FetchError(f"HTTP {status}", status, attempt)
            return FetchResponse(
                url=str(response.url),
                status_code=status,
                content=response.content,
                headers={k.lower(): v for k, v in response.headers.items()},
                attempts=attempt,
            )
        raise AssertionError("unreachable")  # pragma: no cover
