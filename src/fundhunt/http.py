"""Shared HTTP client: identifying User-Agent, timeouts, simple retry.

All sources are keyless public endpoints with no SLA. Transient failures
retry with linear backoff; anything else propagates so `sync` can report
the source as down without hiding it.
"""

from __future__ import annotations

import time

import httpx

from . import __version__

USER_AGENT = (f"fundhunt/{__version__} "
              "(+https://github.com/tacowars/fundhunt; local self-hosted copy)")

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


def client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )


def request(c: httpx.Client, method: str, url: str, *, retries: int = 2,
            backoff: float = 2.0, **kwargs) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = c.request(method, url, **kwargs)
            if resp.status_code in TRANSIENT_STATUSES and attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last  # type: ignore[misc]
