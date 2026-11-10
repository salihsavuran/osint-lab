"""IP geolocation and hosting hints via ip-api.com.

Deliberately a separate collector from :mod:`ip_asn`: it is a different
provider with a different legal posture (free tier is HTTP-only and
non-commercial) and its own rate limit, and mixing them would blur the
attribution in the report.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register

_FIELDS = "status,message,country,countryCode,regionName,city,isp,org,as,timezone,query"


@register
class IPGeoCollector(Collector):
    id = "ip_geo"
    label = "IP geolocation (ip-api.com)"
    description = (
        "Approximate country/region/city plus ISP and organisation for an IP "
        "address. City-level accuracy is indicative, not precise."
    )
    accepts = frozenset({"ip"})
    produces = frozenset()
    legal_basis = (
        "ip-api.com publishes a free, unauthenticated JSON endpoint. Its free "
        "tier is HTTP-only and limited to non-commercial use, which an "
        "educational deployment satisfies."
    )
    attribution = "ip-api.com free tier"
    rate_limit = RateLimit(requests=45, per_seconds=60)
    priority = 50

    def collect(self, ctx: CollectContext) -> CollectorResult:
        ip = ctx.value.strip()
        fetched = ctx.get(
            source=self.id,
            url=f"http://ip-api.com/json/{ip}",
            params={"fields": _FIELDS},
            ttl=86_400,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if not fetched.ok:
            return CollectorResult(notes=[f"ip-api returned HTTP {fetched.status}"])

        try:
            data = fetched.json()
        except ValueError:
            return CollectorResult(notes=["ip-api response was not valid JSON"])

        if data.get("status") != "success":
            return CollectorResult(notes=[f"ip-api: {data.get('message', 'lookup failed')}"])

        facts: list[Fact] = []
        for key, label in (
            ("country", "geo.country"),
            ("regionName", "geo.region"),
            ("city", "geo.city"),
            ("isp", "geo.isp"),
            ("org", "geo.org"),
            ("as", "geo.asn"),
            ("timezone", "geo.timezone"),
        ):
            value = data.get(key)
            if value:
                facts.append(Fact(label, str(value)))

        return CollectorResult(facts=facts)
