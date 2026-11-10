"""Legal entity identity via GLEIF.

The Global Legal Entity Identifier Foundation publishes a free, unauthenticated
API over the LEI registry. This is the cleanest way to pin an organisation to a
jurisdiction and legal form, and the LEI itself is a stable join key across
other datasets.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register


@register
class GLEIFCollector(Collector):
    id = "gleif"
    label = "Legal entity identifier (GLEIF)"
    description = (
        "Resolves an organisation name to LEI records: legal name, jurisdiction, "
        "legal form, registration status and last update date."
    )
    accepts = frozenset({"organization"})
    produces = frozenset()
    legal_basis = (
        "GLEIF operates a public, unauthenticated REST API over the global LEI "
        "index, published for open use."
    )
    attribution = "GLEIF LEI API"
    rate_limit = RateLimit(requests=30, per_seconds=60)
    priority = 20

    def collect(self, ctx: CollectContext) -> CollectorResult:
        name = ctx.value.strip()
        fetched = ctx.get(
            source=self.id,
            url="https://api.gleif.org/api/v1/lei-records",
            params={
                "filter[entity.legalName]": name,
                "page[size]": "5",
            },
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"GLEIF returned HTTP {fetched.status}"])

        try:
            records = fetched.json().get("data", [])
        except ValueError:
            return CollectorResult(notes=["GLEIF response was not valid JSON"])

        if not records:
            return CollectorResult(notes=["no LEI record matched this name"])

        facts: list[Fact] = []
        for record in records[:3]:
            attrs = record.get("attributes", {})
            entity = attrs.get("entity", {})
            lei = attrs.get("lei", record.get("id", ""))

            facts.append(Fact("lei.id", str(lei)))
            legal_name = entity.get("legalName", {}).get("name")
            if legal_name:
                facts.append(Fact("lei.legal_name", str(legal_name)))
            country = entity.get("legalAddress", {}).get("country")
            if country:
                facts.append(Fact("lei.jurisdiction", str(country)))
            legal_form = entity.get("legalForm", {}).get("id")
            if legal_form:
                facts.append(Fact("lei.legal_form", str(legal_form)))
            status = entity.get("status") or attrs.get("registration", {}).get("status")
            if status:
                facts.append(Fact("lei.status", str(status)))
            updated = attrs.get("registration", {}).get("lastUpdateDate")
            if updated:
                facts.append(Fact("lei.last_update", str(updated)))

        return CollectorResult(facts=facts)
