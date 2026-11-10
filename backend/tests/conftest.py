"""Shared test fixtures.

Tests never touch the network. Collectors are exercised against canned
responses, which keeps CI deterministic and keeps us from hammering public
services every time someone pushes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import osintlab.models  # noqa: F401  (registers mappings on Base)
from osintlab.db import Base
from osintlab.evidence import EvidenceStore, digest
from osintlab.fetch import Fetched, FetchError


class FakeFetcher:
    """Stands in for :class:`osintlab.fetch.Fetcher` in tests."""

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict] = []

    def get(
        self,
        *,
        source: str,
        url: str,
        ttl: int = 3600,
        params: dict | None = None,
        headers: dict | None = None,
        limit=None,
        raise_for_status: bool = True,
    ) -> Fetched:
        self.calls.append(
            {"source": source, "url": url, "params": params, "headers": headers}
        )
        if source not in self.responses:
            raise FetchError(f"no canned response for {source}")

        payload = self.responses[source]
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

        return Fetched(
            url=url,
            status=200,
            body=body,
            sha256=digest(body),
            retrieved_at=datetime.now(UTC),
            from_cache=False,
        )


@pytest.fixture
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def store(tmp_path) -> EvidenceStore:
    return EvidenceStore(tmp_path / "evidence")
