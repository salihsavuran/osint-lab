"""OFAC Specially Designated Nationals list.

The US Treasury publishes the SDN list as a bulk CSV for public use. Checking
an organisation against it is a classic compliance-adjacent OSINT exercise, and
the "did this match, and on what basis" question is a good provenance lesson:
a name match is a *lead*, not a conclusion.
"""

from __future__ import annotations

import csv
import io

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register

_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"


@register
class OFACCollector(Collector):
    id = "ofac"
    label = "OFAC sanctions list (SDN)"
    description = (
        "Checks an organisation name against the US Treasury OFAC Specially "
        "Designated Nationals list. A match is a lead requiring manual review, "
        "not an automated determination."
    )
    accepts = frozenset({"organization"})
    produces = frozenset({"sanctions"})
    legal_basis = (
        "The OFAC SDN list is published by the US Department of the Treasury as "
        "a public bulk download for screening purposes."
    )
    attribution = "U.S. Department of the Treasury, OFAC SDN list"
    rate_limit = RateLimit(requests=2, per_seconds=60)
    priority = 80

    def collect(self, ctx: CollectContext) -> CollectorResult:
        needle = ctx.value.strip().lower()
        if len(needle) < 3:
            return CollectorResult(notes=["name too short to screen"])

        fetched = ctx.get(
            source=self.id,
            url=_SDN_URL,
            ttl=604_800,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"OFAC returned HTTP {fetched.status}"])

        facts: list[Fact] = [Fact("ofac.screened_name", ctx.value.strip())]
        links: list[Link] = []
        matches = 0

        reader = csv.reader(io.StringIO(fetched.text(), newline=""))
        for row in reader:
            if len(row) < 4:
                continue
            sdn_name = row[1].strip()
            if needle not in sdn_name.lower():
                continue
            matches += 1
            facts.append(Fact("ofac.match_name", sdn_name))
            facts.append(Fact("ofac.match_program", row[3].strip()))
            if len(row) > 4 and row[4].strip():
                facts.append(Fact("ofac.match_title", row[4].strip()))
            links.append(Link("sanctions", sdn_name, relation="listed_as"))
            if matches >= 5:
                break

        facts.append(Fact("ofac.match_count", str(matches)))
        notes = []
        if matches:
            notes.append(
                "name matches are not identity matches: verify dates of birth, "
                "addresses and identifiers before drawing conclusions"
            )
        return CollectorResult(facts=facts, links=links, notes=notes)
