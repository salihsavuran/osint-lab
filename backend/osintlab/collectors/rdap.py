"""RDAP: the modern, structured replacement for WHOIS.

``rdap.org`` is a bootstrap service that redirects to the authoritative RDAP
server for the registry responsible for a domain. The registry data is
published for public consumption, which is what makes this a safe first
collector.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register


def _vcard_fn(entity: dict) -> str | None:
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2:
        return None
    for item in vcard[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == "fn":
            return str(item[3])
    return None


@register
class RDAPCollector(Collector):
    id = "rdap"
    label = "RDAP (domain registration)"
    description = (
        "Authoritative registration data for a domain: registrar, creation and "
        "expiry dates, nameservers and status codes."
    )
    accepts = frozenset({"domain"})
    produces = frozenset({"domain"})
    legal_basis = (
        "RDAP is a public, unauthenticated protocol published by domain "
        "registries and registrars for the explicit purpose of public lookup "
        "(ICANN gTLD RDAP profile, RFC 9083)."
    )
    attribution = "RDAP bootstrap via rdap.org, authoritative registry response"
    rate_limit = RateLimit(requests=30, per_seconds=60)
    priority = 10

    def collect(self, ctx: CollectContext) -> CollectorResult:
        domain = ctx.value.strip().lower().rstrip(".")
        fetched = ctx.get(
            source=self.id,
            url=f"https://rdap.org/domain/{domain}",
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"RDAP returned HTTP {fetched.status}"])

        try:
            data = fetched.json()
        except ValueError:
            return CollectorResult(notes=["RDAP response was not valid JSON"])

        facts: list[Fact] = []
        links: list[Link] = []

        for event in data.get("events", []):
            action = str(event.get("eventAction", "")).strip()
            date = event.get("eventDate")
            if action and date:
                facts.append(Fact(f"rdap.event.{action.replace(' ', '_')}", str(date)))

        for status in data.get("status", []):
            facts.append(Fact("rdap.status", str(status)))

        for ns in data.get("nameservers", []):
            name = str(ns.get("ldhName", "")).lower().rstrip(".")
            if name:
                facts.append(Fact("rdap.nameserver", name))
                links.append(Link("domain", name, relation="nameserver"))

        for entity in data.get("entities", []):
            roles = "+".join(entity.get("roles", [])) or "entity"
            name = _vcard_fn(entity)
            if name:
                facts.append(Fact(f"rdap.{roles}", name))

        handle = data.get("handle")
        if handle:
            facts.append(Fact("rdap.handle", str(handle)))

        return CollectorResult(facts=facts, links=links)
