"""IP to network context via RIPEstat.

RIPEstat is RIPE NCC's public data API. ``prefix-overview`` maps an address to
its announced prefix and originating ASN(s), which is how you get from "this
domain resolves here" to "this is hosted by that network".
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register


@register
class IPASNCollector(Collector):
    id = "ip_asn"
    label = "IP / ASN context (RIPEstat)"
    description = (
        "Maps an IP address to its announced prefix and originating autonomous "
        "system, including the network holder name."
    )
    accepts = frozenset({"ip"})
    produces = frozenset({"prefix", "asn"})
    legal_basis = (
        "RIPEstat is a public data service published by RIPE NCC for routing "
        "and registry lookups; no authentication is required."
    )
    attribution = "RIPEstat (RIPE NCC) prefix-overview"
    rate_limit = RateLimit(requests=30, per_seconds=60)
    priority = 40

    def collect(self, ctx: CollectContext) -> CollectorResult:
        ip = ctx.value.strip()
        fetched = ctx.get(
            source=self.id,
            url="https://stat.ripe.net/data/prefix-overview/data.json",
            params={"resource": ip},
            ttl=3_600,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"RIPEstat returned HTTP {fetched.status}"])

        try:
            data = fetched.json().get("data", {})
        except ValueError:
            return CollectorResult(notes=["RIPEstat response was not valid JSON"])

        facts: list[Fact] = []
        links: list[Link] = []

        prefix = data.get("resource")
        if prefix:
            facts.append(Fact("net.prefix", str(prefix)))
            links.append(Link("prefix", str(prefix), relation="announced_in"))

        for asn in data.get("asns", []):
            number = asn.get("asn")
            holder = asn.get("holder", "")
            if number is None:
                continue
            value = f"AS{number}"
            facts.append(Fact("net.asn", value))
            if holder:
                facts.append(Fact("net.asn_holder", str(holder)))
            links.append(Link("asn", value, relation="originated_by", display_name=str(holder)))

        for message in fetched.json().get("messages", []):
            if isinstance(message, list) and len(message) >= 2:
                facts.append(Fact("net.note", str(message[1])))

        return CollectorResult(facts=facts, links=links)
