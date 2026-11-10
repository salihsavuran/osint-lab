"""SEC EDGAR: US public company filings.

EDGAR is a public disclosure system. We resolve a company name to its CIK using
the ticker mapping file, then read the submissions index for incorporation
state, SIC industry code and former names.

SEC requires a descriptive User-Agent with contact details and asks clients to
stay under 10 requests per second. Both are enforced here.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register


@register
class EDGARCollector(Collector):
    id = "edgar"
    label = "SEC EDGAR (US company filings)"
    description = (
        "Finds a US public company by name, then reports its CIK, SIC industry, "
        "state of incorporation, fiscal year end and former names."
    )
    accepts = frozenset({"organization"})
    produces = frozenset()
    legal_basis = (
        "EDGAR is the US Securities and Exchange Commission's public disclosure "
        "system. Its data APIs are published for public use under SEC's fair "
        "access policy."
    )
    attribution = "U.S. Securities and Exchange Commission (EDGAR)"
    rate_limit = RateLimit(requests=10, per_seconds=1.0)
    priority = 30

    def _resolve_cik(self, ctx: CollectContext, name: str) -> tuple[int, str] | None:
        fetched = ctx.get(
            source=self.id,
            url="https://www.sec.gov/files/company_tickers.json",
            ttl=604_800,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return None

        try:
            tickers = fetched.json()
        except ValueError:
            return None

        needle = name.strip().lower()
        candidates: list[tuple[int, str]] = []
        for row in tickers.values():
            title = str(row.get("title", ""))
            if needle in title.lower():
                candidates.append((int(row["cik_str"]), title))

        if not candidates:
            return None
        # Prefer an exact match over a substring match.
        for cik, title in candidates:
            if title.lower() == needle:
                return cik, title
        candidates.sort(key=lambda pair: len(pair[1]))
        return candidates[0]

    def collect(self, ctx: CollectContext) -> CollectorResult:
        name = ctx.value.strip()
        resolved = self._resolve_cik(ctx, name)
        if resolved is None:
            return CollectorResult(notes=["no EDGAR company matched this name"])

        cik, title = resolved
        facts: list[Fact] = [
            Fact("edgar.cik", f"{cik:010d}"),
            Fact("edgar.registered_name", title),
        ]

        fetched = ctx.get(
            source=self.id,
            url=f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(facts=facts, notes=[f"EDGAR submissions HTTP {fetched.status}"])

        try:
            data = fetched.json()
        except ValueError:
            return CollectorResult(facts=facts, notes=["EDGAR submissions was not JSON"])

        for key, label in (
            ("sicDescription", "edgar.industry"),
            ("stateOfIncorporation", "edgar.incorporated_in"),
            ("fiscalYearEnd", "edgar.fiscal_year_end"),
            ("category", "edgar.filer_category"),
        ):
            value = data.get(key)
            if value:
                facts.append(Fact(label, str(value)))

        for former in data.get("formerNames", [])[:5]:
            if former.get("name"):
                facts.append(Fact("edgar.former_name", str(former["name"])))

        addresses = data.get("addresses", {}).get("business", {})
        location = ", ".join(
            part for part in (addresses.get("city"), addresses.get("stateOrCountry")) if part
        )
        if location:
            facts.append(Fact("edgar.business_location", location))

        return CollectorResult(facts=facts)
