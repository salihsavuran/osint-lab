"""HTTP fetching with caching, rate limiting, retries and evidence capture.

Every collector goes through :class:`Fetcher`. Nothing talks to the network
directly, which is what makes the politeness rules and the audit trail
enforceable in one place.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from .cache import Cache, cache_key
from .config import Settings
from .config import settings as default_settings
from .evidence import EvidenceStore
from .ratelimit import RateLimit, RateLimiter


class FetchError(RuntimeError):
    """Raised when a source could not be read within the retry budget."""


@dataclass
class Fetched:
    url: str
    status: int
    body: bytes
    sha256: str
    retrieved_at: datetime
    from_cache: bool
    headers: dict[str, str] = field(default_factory=dict)

    def json(self):
        return json.loads(self.body)

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def evidence_ref(self) -> dict[str, object]:
        return {"sha256": self.sha256, "url": self.url, "status": self.status}


class Fetcher:
    def __init__(
        self,
        cache: Cache,
        store: EvidenceStore,
        limiter: RateLimiter | None = None,
        config: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache = cache
        self.store = store
        self.limiter = limiter or RateLimiter()
        self.config = config or default_settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            headers={
                "User-Agent": self.config.user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=self.config.request_timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def get(
        self,
        *,
        source: str,
        url: str,
        ttl: int = 3600,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        limit: RateLimit | None = None,
        raise_for_status: bool = True,
    ) -> Fetched:
        key = cache_key(source, url, params)

        if self.config.offline:
            entry = self.cache.get(key, allow_stale=True)
            if entry is None:
                raise FetchError(
                    f"offline mode: no cached response for {source} {url}"
                )
            return self._from_cache_entry(entry)

        entry = self.cache.get(key)
        if entry is not None:
            return self._from_cache_entry(entry)

        payload, final_url, status, resp_headers = self._request(
            source=source, url=url, params=params, headers=headers, limit=limit
        )

        self.cache.put(
            source=source,
            key=key,
            payload=payload,
            ttl_seconds=ttl,
            url=final_url,
            status=status,
        )
        sha, _path = self.store.store(payload)

        fetched = Fetched(
            url=final_url,
            status=status,
            body=payload,
            sha256=sha,
            retrieved_at=datetime.now(UTC),
            from_cache=False,
            headers=resp_headers,
        )
        if raise_for_status and not fetched.ok:
            raise FetchError(f"{source} returned HTTP {status} for {url}")
        return fetched

    # -- internals ---------------------------------------------------------

    def _from_cache_entry(self, entry) -> Fetched:
        body = self.store.load(entry.sha256)
        return Fetched(
            url=entry.url,
            status=entry.status,
            body=body,
            sha256=entry.sha256,
            retrieved_at=entry.fetched_at,
            from_cache=True,
        )

    def _request(
        self,
        *,
        source: str,
        url: str,
        params: dict[str, str] | None,
        headers: dict[str, str] | None,
        limit: RateLimit | None,
    ) -> tuple[bytes, str, int, dict[str, str]]:
        attempts = self.config.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            if limit is not None:
                self.limiter.acquire(source, limit)

            try:
                response = self.client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(self._backoff(attempt))
                continue

            if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                delay = self._retry_after(response) or self._backoff(attempt)
                time.sleep(delay)
                continue

            return (
                response.content,
                str(response.url),
                response.status_code,
                {k.lower(): v for k, v in response.headers.items()},
            )

        raise FetchError(f"{source}: request to {url} failed: {last_error}")

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0 * (2**attempt), 10.0)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if not raw:
            return None
        try:
            return min(float(raw), 30.0)
        except ValueError:
            return None
