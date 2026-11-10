"""Response cache backed by SQLite metadata + on-disk bodies.

Caching is not an optimisation here, it is a correctness feature:

* public sources throttle aggressively (crt.sh, GDELT),
* a report must be reproducible,
* and CI must never depend on a third party being up.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence import EvidenceStore
from .models import CacheEntry


def cache_key(source: str, url: str, params: dict[str, str] | None) -> str:
    material = json.dumps(
        {"source": source, "url": url, "params": params or {}},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


class Cache:
    def __init__(self, session: Session, store: EvidenceStore) -> None:
        self.session = session
        self.store = store

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        entry = self.session.scalar(select(CacheEntry).where(CacheEntry.cache_key == key))
        if entry is None:
            return None
        if allow_stale:
            return entry

        fetched = entry.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if datetime.now(UTC) - fetched > timedelta(seconds=entry.ttl_seconds):
            return None
        return entry

    def put(
        self,
        *,
        source: str,
        key: str,
        payload: bytes,
        ttl_seconds: int,
        url: str = "",
        status: int = 200,
    ) -> CacheEntry:
        sha, path = self.store.store(payload)
        entry = self.session.scalar(select(CacheEntry).where(CacheEntry.cache_key == key))
        if entry is None:
            entry = CacheEntry(
                source=source,
                cache_key=key,
                url=url,
                status=status,
                fetched_at=datetime.now(UTC),
                ttl_seconds=ttl_seconds,
                body_path=path,
                sha256=sha,
            )
            self.session.add(entry)
        else:
            entry.url = url
            entry.status = status
            entry.fetched_at = datetime.now(UTC)
            entry.ttl_seconds = ttl_seconds
            entry.body_path = path
            entry.sha256 = sha
        self.session.flush()
        return entry
