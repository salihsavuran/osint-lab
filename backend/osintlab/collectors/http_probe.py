"""HTTP probe: headers, redirect chain and basic technology hints.

This is the one collector that touches the target's own server. It behaves
like a browser: one GET per scheme, a descriptive User-Agent, no path guessing,
no authentication, no aggressive fuzzing.
"""

from __future__ import annotations

from ..fetch import FetchError
from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, Link, register

_INTERESTING_HEADERS = {
    "server": "http.server",
    "x-powered-by": "http.powered_by",
    "content-type": "http.content_type",
    "via": "http.via",
    "cf-ray": "http.cdn_cloudflare",
    "x-vercel-id": "http.cdn_vercel",
    "x-amz-cf-id": "http.cdn_cloudfront",
}

_SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
)


@register
class HTTPProbeCollector(Collector):
    id = "http_probe"
    label = "HTTP headers and redirects"
    description = (
        "Requests the target over HTTPS (and HTTP if HTTPS fails) and records "
        "status, redirect destination, server headers and security headers."
    )
    accepts = frozenset({"domain", "url"})
    produces = frozenset({"url"})
    legal_basis = (
        "A single unauthenticated GET request to a publicly reachable web "
        "server, equivalent to visiting the site. No crawling, no path "
        "enumeration, no authentication bypass."
    )
    attribution = "Direct HTTP request to the target"
    rate_limit = RateLimit(requests=20, per_seconds=60)
    priority = 60

    def collect(self, ctx: CollectContext) -> CollectorResult:
        if ctx.entity_type == "url":
            candidates = [ctx.value]
        else:
            host = ctx.value.strip().lower()
            candidates = [f"https://{host}/", f"http://{host}/"]

        facts: list[Fact] = []
        links: list[Link] = []
        notes: list[str] = []

        for candidate in candidates:
            try:
                fetched = ctx.get(
                    source=self.id,
                    url=candidate,
                    ttl=3_600,
                    limit=self.rate_limit,
                    raise_for_status=False,
                )
            except FetchError as exc:
                notes.append(f"{candidate}: {exc}")
                continue

            facts.append(Fact("http.probed_url", candidate))
            facts.append(Fact("http.status", str(fetched.status)))

            if fetched.url and fetched.url != candidate:
                facts.append(Fact("http.final_url", fetched.url))
                links.append(Link("url", fetched.url, relation="redirects_to"))

            for header, label in _INTERESTING_HEADERS.items():
                value = fetched.headers.get(header)
                if value:
                    facts.append(Fact(label, value[:300]))

            present = [
                h for h in _SECURITY_HEADERS if h in fetched.headers
            ]
            facts.append(Fact("http.security_headers_present", ",".join(present) or "none"))

            if fetched.ok:
                # One successful scheme is enough; don't hammer both.
                break

        return CollectorResult(facts=facts, links=links, notes=notes)
