"""Collector contract and registry.

A collector is a small, self-describing unit of collection. It must declare:

* which entity types it accepts and produces,
* the legal basis for reading the source,
* the source's published rate limit,
* and how it should be attributed in a report.

Those declarations are not documentation — the runner enforces the rate limit
and the report generator reads the legal basis. A collector that cannot state
its basis does not get registered.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..config import Settings
from ..fetch import Fetched, Fetcher
from ..ratelimit import RateLimit


@dataclass
class CollectContext:
    entity_type: str
    value: str
    fetcher: Fetcher
    settings: Settings
    evidence: list[Fetched] = field(default_factory=list)

    def get(self, **kwargs) -> Fetched:
        """Fetch through the shared client and record the evidence automatically."""
        fetched = self.fetcher.get(**kwargs)
        self.evidence.append(fetched)
        return fetched


@dataclass(frozen=True)
class Fact:
    """A single attributed key/value observation."""

    key: str
    value: str
    confidence: float = 0.9


@dataclass(frozen=True)
class Link:
    """A relationship to another entity, discovered while collecting."""

    type: str
    value: str
    relation: str = "related"
    display_name: str = ""


@dataclass
class CollectorResult:
    facts: list[Fact] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Collector(ABC):
    id: str = ""
    label: str = ""
    description: str = ""
    accepts: frozenset[str] = frozenset()
    produces: frozenset[str] = frozenset()
    legal_basis: str = ""
    attribution: str = ""
    rate_limit: RateLimit = RateLimit(requests=30, per_seconds=60)
    #: Higher runs first; cheap/authoritative sources lead the pipeline.
    priority: int = 50

    @abstractmethod
    def collect(self, ctx: CollectContext) -> CollectorResult:
        """Read the source and return facts plus discovered links."""


_REGISTRY: dict[str, type[Collector]] = {}


def register(cls: type[Collector]) -> type[Collector]:
    if not cls.id:
        raise ValueError(f"{cls.__name__} must define an id")
    if not cls.legal_basis:
        raise ValueError(f"{cls.__name__} must declare a legal_basis")
    if not cls.accepts:
        raise ValueError(f"{cls.__name__} must declare accepted entity types")
    if cls.id in _REGISTRY:
        raise ValueError(f"duplicate collector id: {cls.id}")
    _REGISTRY[cls.id] = cls
    return cls


def load_builtin() -> None:
    """Import the bundled collectors so they self-register."""
    from . import (  # noqa: F401
        crtsh,
        dns_doh,
        edgar,
        gleif,
        http_probe,
        ip_asn,
        ip_geo,
        ofac,
        rdap,
        wayback,
        wikidata,
    )


def all_collectors() -> dict[str, Collector]:
    if not _REGISTRY:
        load_builtin()
    return {cid: cls() for cid, cls in sorted(_REGISTRY.items())}


def get_collector(collector_id: str) -> Collector:
    collectors = all_collectors()
    try:
        return collectors[collector_id]
    except KeyError:
        known = ", ".join(collectors)
        raise KeyError(f"unknown collector {collector_id!r}; known: {known}") from None


def collectors_for(entity_type: str) -> list[Collector]:
    return [c for c in all_collectors().values() if entity_type in c.accepts]
