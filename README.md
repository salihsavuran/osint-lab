# osint-lab

An educational OSINT workbench where **every fact is attributed**. Point it at a
domain, an IP address or an organisation; it collects from public sources, stores
the raw evidence, and produces a report with a citation for every claim.

Built for people learning OSINT methodology — students, journalists, security
folks — not for automating surveillance.

```
$ osintlab collect example.com --case 1

┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ collector  ┃ status ┃ facts ┃ links ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ rdap       │ ok     │    11 │     2 │
│ dns_doh    │ ok     │    10 │     4 │
│ crtsh      │ ok     │     3 │     5 │
│ http_probe │ ok     │     6 │     0 │
│ wayback    │ ok     │     4 │     0 │
└────────────┴────────┴───────┴───────┘
```

## Why this exists

Most "OSINT tools" are scrapers with a UI. They produce a wall of unverified
output and teach nothing about whether any of it is true.

osint-lab makes the opposite trade. Every attribute carries:

- the **source** that produced it,
- the **time** it was retrieved,
- the **method** used,
- a **SHA-256 digest** of the exact raw response, stored on disk.

So when a report says "this domain was registered in 1995", you can open the
RDAP response that said so, verify its hash, and see exactly when it was fetched.

## What it is not

There is no breach-data lookup, no facial recognition, no proxy rotation, no
fingerprint spoofing, no login-walled scraping, and no tooling for assembling a
profile on a private individual. See [ETHICS.md](ETHICS.md) for the reasoning.

Scope is **infrastructure** (domains, IPs, certificates, networks) and
**organisations** (registries, filings, sanctions lists). A person's name can
appear as an officer attached to a public filing, but nothing enriches it.

## Quickstart

Requirements: Python 3.12+ and Node 20+ (Node only for the web UI).

```bash
git clone https://github.com/salihsavuran/osint-lab.git
cd osint-lab

python3 -m venv .venv
.venv/bin/pip install -e 'backend[dev]'

# create the database
.venv/bin/osintlab init

# list what can be collected, and on what legal basis
.venv/bin/osintlab sources

# run a case
.venv/bin/osintlab case create \
  --title "Infrastructure review: example.com" \
  --scope "example.com is IANA's reserved documentation domain"

.venv/bin/osintlab collect example.com --case 1

# inspect
.venv/bin/osintlab case show 1
.venv/bin/osintlab graph --case 1 --format dot | dot -Tsvg > graph.svg
.venv/bin/osintlab report --case 1 --out report.md
```

### Web UI

```bash
# terminal 1 — API on :8000
.venv/bin/osintlab serve

# terminal 2 — dev server on :5173, proxies /api to :8000
cd frontend && npm install && npm run dev
```

For a single-process deployment, build the UI first and `osintlab serve` will
serve it from `/`:

```bash
cd frontend && npm install && npm run build && cd ..
.venv/bin/osintlab serve
# open http://127.0.0.1:8000
```

## Collectors

All of these are public and need no API keys. One of them — `phone_number` —
runs entirely offline.

| id | Source | Accepts | What you get |
| --- | --- | --- | --- |
| `rdap` | rdap.org | domain | Registrar, registration/expiry dates, nameservers, status |
| `dns_doh` | Cloudflare DoH | domain | A, AAAA, MX, NS, TXT, CNAME, SPF, DMARC |
| `crtsh` | Certificate Transparency | domain | Subdomains from CT logs |
| `ip_asn` | RIPEstat | ip | Announced prefix, originating ASN, holder |
| `ip_geo` | ip-api.com | ip | Country, region, city, ISP, organisation |
| `http_probe` | target itself | domain, url | Status, redirects, server headers, security headers |
| `wayback` | Internet Archive | domain, url | First and last archived snapshot |
| `gleif` | GLEIF | organization | LEI, jurisdiction, legal form, status |
| `edgar` | SEC EDGAR | organization | CIK, SIC industry, incorporation state, former names |
| `ofac` | US Treasury | organization | Sanctions list name matches (leads, not verdicts) |
| `wikidata` | Wikidata | organization | Description, official site, country, industry |
| `phone_number` | libphonenumber (bundled) | phone | Validity, country, region, line type, allocated carrier, timezones — offline |

Every collector declares its rate limit, and the runner enforces it. Responses
are cached with a per-source TTL.

`phone_number` is the exception to "fetches from the web": it reads numbering-plan
metadata bundled with the library, so it makes no network request at all. It
describes the **number**, never the subscriber — see [ETHICS.md](ETHICS.md#phone-numbers).

## How it works

```
Scope + case  ──▶  Collectors  ──▶  Provenance + evidence  ──▶  Graph  ──▶  Cited report
                        │
                  cache · rate limits · retries
```

```
backend/osintlab/
├── collectors/     one module per source, self-registering
├── service.py      orchestration: facts -> entities, edges, provenance
├── fetch.py        the only code that touches the network
├── cache.py        per-source TTL cache
├── ratelimit.py    sliding-window limiter
├── evidence.py     content-addressed raw response store
├── graph.py        entity/edge projection (JSON + DOT)
├── report.py       Markdown report with bibliography
├── cli.py          typer CLI
└── api/app.py      FastAPI
```

The data model is four tables plus two: `Case → Entity → Attribute → Provenance`,
`Edge`, `AuditEvent`, `CacheEntry`.

See [docs/architecture.md](docs/architecture.md) for the design rationale and
[docs/collectors.md](docs/collectors.md) for per-source notes and limitations.

## Configuration

Copy `.env.example` to `.env`. Everything is optional; the important one is:

```bash
OSINTLAB_USER_AGENT=osint-lab/0.1 (educational; contact: you@example.org)
```

Several sources (SEC EDGAR in particular) require a descriptive User-Agent with
a contact address. Set it before collecting.

`OSINTLAB_OFFLINE=true` makes the tool serve cached responses only — useful for
classroom demos and reproducible exercises.

## Exercises

Three guided missions that use only public data and are safe to run:

1. [Map a domain's infrastructure](docs/missions/01-domain-infrastructure.md)
2. [Trace a corporate identity](docs/missions/02-corporate-identity.md)
3. [Verify a claim across independent sources](docs/missions/03-source-verification.md)

## Roadmap

- [x] Provenance model, evidence store, cited reports
- [x] 12 collectors, all keyless
- [x] CLI + HTTP API + web UI
- [ ] Geo map view (Leaflet) for IP entities
- [ ] Optional keyed collectors (Shodan, Censys, Companies House)
- [ ] PDF export
- [ ] Postgres deployment guide

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [ETHICS.md](ETHICS.md). A new
collector must declare its legal basis — the registry refuses it otherwise.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
