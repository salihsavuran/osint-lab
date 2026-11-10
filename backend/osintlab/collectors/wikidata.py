"""Wikidata: structured background on organisations.

Wikidata is the least authoritative and most useful source in the set. It gives
you a fast, linked starting point (official website, country, industry,
inception) that you then have to corroborate. That tension is the lesson.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register

_API = "https://www.wikidata.org/w/api.php"

# Wikidata property -> fact key
_PROPERTIES = {
    "P856": "wikidata.official_website",
    "P571": "wikidata.inception",
    "P17": "wikidata.country",
    "P452": "wikidata.industry",
    "P159": "wikidata.headquarters",
    "P1128": "wikidata.employees",
}


def _claim_value(claim: dict):
    mainsnak = claim.get("mainsnak", {})
    value = mainsnak.get("datavalue", {}).get("value")
    if isinstance(value, dict):
        if "time" in value:
            return str(value["time"]).lstrip("+")[:10]
        if "amount" in value:
            return str(value["amount"]).lstrip("+")
        if "id" in value:
            return str(value["id"])
        if "text" in value:
            return str(value["text"])
    return str(value) if value is not None else None


@register
class WikidataCollector(Collector):
    id = "wikidata"
    label = "Wikidata entity"
    description = (
        "Looks an organisation up on Wikidata and returns its description, "
        "official website, country, industry and inception date."
    )
    accepts = frozenset({"organization"})
    produces = frozenset()
    legal_basis = (
        "Wikidata is a free, openly licensed knowledge base (CC0) with a public "
        "MediaWiki API intended for programmatic reuse."
    )
    attribution = "Wikidata (CC0)"
    rate_limit = RateLimit(requests=30, per_seconds=60)
    priority = 90

    def collect(self, ctx: CollectContext) -> CollectorResult:
        name = ctx.value.strip()
        search = ctx.get(
            source=self.id,
            url=_API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": "1",
                "format": "json",
            },
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not search.ok:
            return CollectorResult(notes=[f"Wikidata search HTTP {search.status}"])

        try:
            hits = search.json().get("search", [])
        except ValueError:
            return CollectorResult(notes=["Wikidata search was not valid JSON"])

        if not hits:
            return CollectorResult(notes=["no Wikidata item matched this name"])

        qid = hits[0]["id"]
        facts: list[Fact] = [Fact("wikidata.qid", qid)]
        if hits[0].get("description"):
            facts.append(Fact("wikidata.description", hits[0]["description"]))

        entity = ctx.get(
            source=self.id,
            url=_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|claims",
                "languages": "en",
                "format": "json",
            },
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not entity.ok:
            return CollectorResult(facts=facts, notes=[f"Wikidata entity HTTP {entity.status}"])

        try:
            payload = entity.json().get("entities", {}).get(qid, {})
        except ValueError:
            return CollectorResult(facts=facts, notes=["Wikidata entity was not JSON"])

        label = payload.get("labels", {}).get("en", {}).get("value")
        if label:
            facts.append(Fact("wikidata.label", label))

        claims = payload.get("claims", {})
        qids_to_resolve: set[str] = set()
        for prop, key in _PROPERTIES.items():
            for claim in claims.get(prop, [])[:2]:
                value = _claim_value(claim)
                if not value:
                    continue
                facts.append(Fact(key, value))
                if value.startswith("Q") and value[1:].isdigit():
                    qids_to_resolve.add(value)

        # Resolve the referenced QIDs to human-readable labels in one call.
        if qids_to_resolve:
            resolved = ctx.get(
                source=self.id,
                url=_API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(sorted(qids_to_resolve)[:10]),
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                },
                ttl=86_400,
                limit=self.rate_limit,
                raise_for_status=False,
            )
            if resolved.ok:
                try:
                    entities = resolved.json().get("entities", {})
                    for ref_qid, ref in entities.items():
                        ref_label = ref.get("labels", {}).get("en", {}).get("value")
                        if ref_label:
                            facts.append(Fact("wikidata.reference", f"{ref_qid}={ref_label}"))
                except ValueError:
                    pass

        return CollectorResult(facts=facts)
