"""Certificate Transparency logs via crt.sh.

Every publicly trusted TLS certificate is logged. Searching the logs for
``%.example.com`` reveals subdomains that were never linked anywhere, including
staging hosts and long-forgotten internal names.

This is the single highest-value free source for infrastructure mapping, and
also the one most likely to throttle you, hence the conservative rate limit and
a 24h cache.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register


def _clean_name(raw: str) -> list[str]:
    names = []
    for line in str(raw).splitlines():
        name = line.strip().lower().lstrip("*.").rstrip(".")
        if name and " " not in name and "@" not in name:
            names.append(name)
    return names


@register
class CrtShCollector(Collector):
    id = "crtsh"
    label = "Certificate Transparency (crt.sh)"
    description = (
        "Finds subdomains of a domain by searching public Certificate "
        "Transparency logs."
    )
    accepts = frozenset({"domain"})
    produces = frozenset({"domain"})
    legal_basis = (
        "Certificate Transparency logs are append-only public records that CAs "
        "are required to publish. crt.sh exposes them through a public search "
        "interface intended for exactly this kind of query."
    )
    attribution = "crt.sh Certificate Transparency search"
    rate_limit = RateLimit(requests=6, per_seconds=60)
    priority = 30

    def collect(self, ctx: CollectContext) -> CollectorResult:
        domain = ctx.value.strip().lower().rstrip(".")
        fetched = ctx.get(
            source=self.id,
            url="https://crt.sh/",
            params={"q": f"%.{domain}", "output": "json"},
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"crt.sh returned HTTP {fetched.status}"])

        try:
            rows = fetched.json()
        except ValueError:
            return CollectorResult(notes=["crt.sh did not return JSON (rate limited?)"])

        if not isinstance(rows, list):
            return CollectorResult(notes=["crt.sh returned an unexpected payload"])

        facts: list[Fact] = [Fact("ct.certificates", str(len(rows)))]
        links: list[Link] = []
        seen: set[str] = set()

        for row in rows:
            if not isinstance(row, dict):
                continue
            for candidate in _clean_name(row.get("name_value", "")):
                if candidate == domain or candidate.endswith("." + domain) is False:
                    continue
                if candidate in seen:
                    continue
                seen.add(candidate)
                links.append(Link("domain", candidate, relation="certificate_san"))

            issuer = row.get("issuer_name")
            if issuer and "ct.issuers" not in {f.key for f in facts}:
                facts.append(Fact("ct.issuers", str(issuer)[:200]))

        facts.append(Fact("ct.unique_names", str(len(seen))))
        return CollectorResult(facts=facts, links=links)
