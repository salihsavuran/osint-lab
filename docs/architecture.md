# Architecture

## The problem being solved

A scraper can produce output. It cannot produce *trust*. Once you are several
pivots deep into an investigation, the question is no longer "what did I find"
but "how do I know this is true, and when did I learn it".

osint-lab is built around that second question. The architecture follows from a
single constraint: **no fact may exist in the database without a pointer to the
bytes that produced it.**

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  CLI (typer)              Web UI (SvelteKit)             │
└───────────────┬───────────────────────┬──────────────────┘
                │                       │
        ┌───────▼───────────────────────▼───────┐
        │  FastAPI  /api/*                      │
        └───────────────┬───────────────────────┘
                        │
        ┌───────────────▼───────────────────────┐
        │  CollectorService                     │
        │  orchestration · provenance · audit   │
        └───┬───────────┬───────────┬───────────┘
            │           │           │
   ┌────────▼──┐  ┌─────▼─────┐  ┌──▼──────────┐
   │ Collectors│  │  Cache    │  │  Evidence   │
   │ (11)      │  │  (SQLite  │  │  store      │
   │           │  │   + files)│  │  (SHA-256)  │
   └─────┬─────┘  └───────────┘  └─────────────┘
         │
   ┌─────▼─────────────────────────────────────┐
   │  Fetcher — the only network egress        │
   │  rate limits · retries · UA · caching     │
   └───────────────────────────────────────────┘
```

## Data model

```
Case ──< Entity ──< Attribute >── Provenance
  │                                  
  ├──< Edge (source → target, relation, provenance)
  └──< AuditEvent
```

| Table | Purpose |
| --- | --- |
| `cases` | One investigation, with a scope note |
| `entities` | Domain, ip, prefix, asn, url, organization, sanctions |
| `attributes` | A single key/value observation on an entity |
| `provenance` | Source, URL, timestamp, method, confidence, evidence digest, legal basis |
| `edges` | Typed relationships between entities |
| `audit_events` | Every collection start/finish/error |
| `cache_entries` | Cache metadata; bodies live on disk |

`Entity` is unique on `(case_id, type, value)`, which is what makes repeated
runs idempotent. `Attribute` is deduplicated on `(entity_id, key, value)` at
write time, so re-running a collector does not inflate the report.

## Why synchronous

Collectors are I/O bound, but a single collection run is seconds long and the
tool is single-user. An async stack would add a scheduler, a job store and a
class of cancellation bugs in exchange for concurrency that nobody needs here.
SQLAlchemy's sync API plus `httpx.Client` keeps one code path shared by CLI,
API and tests.

If a future version needs background jobs, the seam is `CollectorService.run` —
nothing above it assumes synchronous completion.

## Why evidence is content-addressed

```
payload ──▶ sha256 ──▶ <data_dir>/evidence/<sha256>.bin
```

Two responses with identical bytes share one file. A provenance row stores the
SHA-256, so a report can be checked against the store. `OSINTLAB_OFFLINE=true`
replays the cache, which is what makes classroom demos reproducible and CI
network-free.

## Provenance granularity

Provenance is recorded **per collector run**, not per HTTP response. A run that
makes seven DNS queries produces one provenance row whose `evidence_refs` lists
all seven responses with their digests, and whose `raw_sha256` is the digest of
the concatenated per-response digests.

This is a deliberate trade-off: per-fact provenance would mean a row per
attribute and a much larger schema. The current model still answers "which
source, when, and can I see the bytes" — and the report shows the full evidence
manifest. If you need per-response attribution for a specific collector, give
that collector a narrower scope.

## Extending

New sources implement the `Collector` protocol. The registry rejects a collector
that does not declare a legal basis, accepted types or a valid rate limit. That
check is the main defence against the project drifting into something it should
not be.

## Non-goals

- Distributed crawling
- Evasion (proxies, fingerprint spoofing, CAPTCHA solving)
- Person-centric aggregation
- Real-time monitoring / alerting
