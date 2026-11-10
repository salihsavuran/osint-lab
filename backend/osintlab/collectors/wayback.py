"""Wayback Machine snapshot history via the CDX API.

Tells you whether a site existed before it claimed to, and when its content
changed. Two cheap queries (first and last snapshot) rather than downloading
the whole index.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register


@register
class WaybackCollector(Collector):
    id = "wayback"
    label = "Wayback Machine history"
    description = (
        "First and last archived snapshot of a URL, plus the total snapshot "
        "count, from the Internet Archive's CDX index."
    )
    accepts = frozenset({"domain", "url"})
    produces = frozenset()
    legal_basis = (
        "The Internet Archive publishes the CDX server API for public, "
        "programmatic access to its web archive index."
    )
    attribution = "Internet Archive Wayback Machine CDX API"
    rate_limit = RateLimit(requests=10, per_seconds=60)
    priority = 70

    def _query(self, ctx: CollectContext, target: str, limit: str) -> list[list[str]]:
        fetched = ctx.get(
            source=self.id,
            url="https://web.archive.org/cdx/search/cdx",
            params={
                "url": target,
                "output": "json",
                "fl": "timestamp,original,statuscode",
                "limit": limit,
                "collapse": "timestamp:8",
            },
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return []
        try:
            rows = fetched.json()
        except ValueError:
            return []
        if not isinstance(rows, list) or not rows:
            return []
        return rows[1:]

    def collect(self, ctx: CollectContext) -> CollectorResult:
        target = ctx.value.strip()
        facts: list[Fact] = []
        notes: list[str] = []

        first = self._query(ctx, target, "1")
        last = self._query(ctx, target, "-1")

        if first:
            facts.append(Fact("archive.first_snapshot", first[0][0]))
            facts.append(Fact("archive.first_url", first[0][1]))
        if last:
            facts.append(Fact("archive.last_snapshot", last[0][0]))
            facts.append(Fact("archive.last_url", last[0][1]))

        if not first and not last:
            notes.append("no archived snapshots found")

        return CollectorResult(facts=facts, notes=notes)
