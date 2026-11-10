# Collector reference

Per-source notes: what it returns, its published limit, and where it lies to
you. The last part is the point — every source has a blind spot, and a report
that does not acknowledge it is worse than no report.

---

## `rdap` — RDAP

**Endpoint:** `https://rdap.org/domain/<domain>` (302 to the authoritative registry)
**Accepts:** domain · **Rate:** 30/min · **Cache:** 24h

Returns registrar, creation/expiry/last-changed events, nameservers, status
codes, and registrar contact name.

**Limits:** registrant details are redacted in most gTLDs since GDPR. Do not
expect a name. RDAP coverage is good for gTLDs and growing for ccTLDs; some
registries still only speak WHOIS.

---

## `dns_doh` — DNS over HTTPS

**Endpoint:** `https://cloudflare-dns.com/dns-query` (JSON, `Accept: application/dns-json`)
**Accepts:** domain · **Rate:** 60/min · **Cache:** 1h

A, AAAA, MX, NS, TXT, CNAME, plus `_dmarc.<domain>` TXT. Flags SPF presence.

**Limits:** Cloudflare's resolver is a *recursive* resolver, so you see what it
sees, not what the authoritative server would say to you from your own network.
GeoDNS means the A records you get may differ from the target's real users.
CNAME chains are only partially followed.

---

## `crtsh` — Certificate Transparency

**Endpoint:** `https://crt.sh/?q=%.<domain>&output=json`
**Accepts:** domain · **Rate:** 6/min · **Cache:** 24h

Subdomains harvested from CT log entries, plus certificate count and issuer.

**Limits:** the highest-value and least reliable source here. crt.sh is often
overloaded and returns HTML or 503 under load — the collector reports that as a
note rather than failing the run. CT logs only contain names that had a
publicly-trusted certificate issued, so internal-only names never appear.
Wildcard entries are stripped, which can hide structure.

---

## `ip_asn` — RIPEstat

**Endpoint:** `https://stat.ripe.net/data/prefix-overview/data.json?resource=<ip>`
**Accepts:** ip · **Rate:** 30/min · **Cache:** 1h

Announced prefix, originating ASN(s), holder name, and routing notes.

**Limits:** reflects *routing*, not ownership. An IP can be announced by a
different ASN than the one that owns it (transit, anycast, hijack). "Not
announced" responses are aligned to the covering prefix, which the collector
records as a note.

---

## `ip_geo` — ip-api.com

**Endpoint:** `http://ip-api.com/json/<ip>`
**Accepts:** ip · **Rate:** 45/min · **Cache:** 24h

Country, region, city, ISP, organisation, ASN, timezone.

**Limits:** the free tier is HTTP-only (no TLS) and non-commercial only. City
accuracy is approximate and frequently wrong for VPNs, mobile networks and
anycast. Treat city-level data as a hint, never as a location claim. If you need
accuracy or HTTPS, use a paid provider.

---

## `http_probe` — direct request

**Endpoint:** the target itself
**Accepts:** domain, url · **Rate:** 20/min · **Cache:** 1h

Status, final URL after redirects, `Server`, `X-Powered-By`, CDN headers, and
which security headers are present.

**Limits:** this is the only collector that touches the target's own server, and
it sends exactly one GET per scheme. Behind Cloudflare or similar, the `Server`
header describes the CDN, not the origin. Absence of a security header may mean
the CDN stripped it.

---

## `wayback` — Internet Archive CDX

**Endpoint:** `https://web.archive.org/cdx/search/cdx`
**Accepts:** domain, url · **Rate:** 10/min · **Cache:** 24h

First and last snapshot timestamp and URL.

**Limits:** two queries, not the whole index. "First snapshot" is the first the
Archive *crawled*, which is not necessarily when the site was created. Absence of
snapshots proves nothing — robots.txt exclusions and crawl gaps are common.

---

## `gleif` — Legal Entity Identifier

**Endpoint:** `https://api.gleif.org/api/v1/lei-records`
**Accepts:** organization · **Rate:** 30/min · **Cache:** 24h

LEI, legal name, jurisdiction, legal form, registration status, last update.

**Limits:** only entities that have obtained an LEI, which skews towards
regulated financial entities. Name search is fuzzy — verify the jurisdiction and
legal form before accepting a match.

---

## `edgar` — SEC EDGAR

**Endpoint:** `https://data.sec.gov/submissions/CIK##########.json`
**Accepts:** organization · **Rate:** 10/s · **Cache:** 24h

CIK, registered name, SIC industry, state of incorporation, fiscal year end,
former names, business location.

**Limits:** US-listed companies only. The ticker file is large (~1 MB) but cached
for a week. SEC requires a descriptive User-Agent with contact details — set
`OSINTLAB_USER_AGENT` before using this. Business address is the registered
address, not where anyone actually works.

---

## `ofac` — SDN sanctions list

**Endpoint:** `https://www.treasury.gov/ofac/downloads/sdn.csv`
**Accepts:** organization · **Rate:** 2/min · **Cache:** 7d

Name matches against the SDN list, with program and title.

**Limits:** a substring name match is **not** an identity match. Common names
produce false positives constantly. OFAC publishes dates of birth, addresses and
passport numbers in `sdn_comments`/`alt` files precisely because names alone are
insufficient. The collector says this in its own output. Never report a sanctions
match without corroborating identifiers.

---

## `wikidata` — structured background

**Endpoint:** `https://www.wikidata.org/w/api.php`
**Accepts:** organization · **Rate:** 30/min · **Cache:** 24h

Description, label, official website, country, industry, headquarters,
inception, employee count, with referenced QIDs resolved to labels.

**Limits:** crowd-edited. The least authoritative source in the set and the most
convenient. Use it to generate leads, then verify each claim against a primary
source. Vandalism and stale data are real.

---

## Adding a source

See [CONTRIBUTING.md](../CONTRIBUTING.md). The registry enforces a declared
legal basis and a valid rate limit at import time.
