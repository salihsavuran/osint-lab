"""DNS over HTTPS via Cloudflare's public resolver.

DoH gives structured JSON instead of parsing dig output, works through
restrictive networks, and needs no API key. We resolve the record types that
actually matter for infrastructure mapping.
"""

from __future__ import annotations

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register

# DNS RR type -> (name, how to interpret the answer)
RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME")

_IP_TYPES = {"A", "AAAA"}
_DOMAIN_TYPES = {"MX", "NS", "CNAME"}


@register
class DNSDoHCollector(Collector):
    id = "dns_doh"
    label = "DNS records (DoH)"
    description = (
        "Resolves A, AAAA, MX, NS, TXT and CNAME records through Cloudflare's "
        "public DNS-over-HTTPS endpoint."
    )
    accepts = frozenset({"domain"})
    produces = frozenset({"ip", "domain"})
    legal_basis = (
        "Public recursive DNS resolution. The queries are ordinary DNS lookups "
        "against a resolver that publishes a JSON API (RFC 8484 / Google & "
        "Cloudflare DoH JSON interface)."
    )
    attribution = "Cloudflare 1.1.1.1 DNS-over-HTTPS resolver"
    rate_limit = RateLimit(requests=60, per_seconds=60)
    priority = 20

    def collect(self, ctx: CollectContext) -> CollectorResult:
        domain = ctx.value.strip().lower().rstrip(".")
        facts: list[Fact] = []
        links: list[Link] = []
        notes: list[str] = []

        for rtype in RECORD_TYPES:
            fetched = ctx.get(
                source=self.id,
                url="https://cloudflare-dns.com/dns-query",
                params={"name": domain, "type": rtype},
                headers={"Accept": "application/dns-json"},
                ttl=3_600,
                limit=self.rate_limit,
                raise_for_status=False,
            )
            if not fetched.ok:
                notes.append(f"{rtype}: HTTP {fetched.status}")
                continue

            try:
                data = fetched.json()
            except ValueError:
                notes.append(f"{rtype}: invalid JSON")
                continue

            answers = data.get("Answer") or []
            if not answers and data.get("Status") not in (0, None):
                notes.append(f"{rtype}: DNS status {data.get('Status')}")

            for answer in answers:
                raw = str(answer.get("data", "")).strip()
                if not raw:
                    continue

                if rtype in _IP_TYPES:
                    facts.append(Fact(f"dns.{rtype.lower()}", raw))
                    links.append(Link("ip", raw, relation="resolves_to"))
                elif rtype in _DOMAIN_TYPES:
                    # MX records are prefixed with a priority: "10 mail.example.com."
                    target = raw.split()[-1].lower().rstrip(".")
                    if target:
                        facts.append(Fact(f"dns.{rtype.lower()}", target))
                        relation = "mail_exchange" if rtype == "MX" else "nameserver"
                        links.append(Link("domain", target, relation=relation))
                else:  # TXT
                    facts.append(Fact("dns.txt", raw.strip('"')))

        # Flag the authentication records that are easy to miss by eye.
        txt_values = [f.value for f in facts if f.key == "dns.txt"]
        if any(v.startswith("v=spf1") for v in txt_values):
            facts.append(Fact("email.spf", "present"))

        # DMARC lives at _dmarc.<domain>, so it needs its own query.
        dmarc = ctx.get(
            source=self.id,
            url="https://cloudflare-dns.com/dns-query",
            params={"name": f"_dmarc.{domain}", "type": "TXT"},
            headers={"Accept": "application/dns-json"},
            ttl=3_600,
            limit=self.rate_limit,
            raise_for_status=False,
        )
        if dmarc.ok:
            try:
                for answer in dmarc.json().get("Answer") or []:
                    value = str(answer.get("data", "")).strip('"')
                    if value.startswith("v=DMARC1"):
                        facts.append(Fact("email.dmarc", value))
            except ValueError:
                pass

        return CollectorResult(facts=facts, links=links, notes=notes)
