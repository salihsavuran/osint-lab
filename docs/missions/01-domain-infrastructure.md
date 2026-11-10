# Mission 1 — Map a domain's infrastructure

**Goal:** build a defensible picture of where a domain lives and what it exposes.

**Target:** `example.com` (IANA's reserved documentation domain — safe to probe).

**Time:** 20 minutes.

## Setup

```bash
.venv/bin/osintlab init
.venv/bin/osintlab case create \
  --title "Mission 1: example.com infrastructure" \
  --scope "example.com is reserved by IANA for documentation (RFC 2606)"
.venv/bin/osintlab collect example.com --case 1
```

## Questions to answer

1. Who is the registrar, and when was the domain registered?
2. Which IP addresses does it resolve to, and who announces those addresses?
3. What does the certificate transparency log reveal about subdomains?
4. What does the HTTP response tell you about the hosting provider?
5. When was the site first archived?

## What to notice

- **RDAP redaction.** You will not find a registrant name. Why not, and what
  does that mean for attribution?
- **Anycast.** `example.com` resolves to Cloudflare addresses. The ASN holder is
  the network operator, not the site owner. These are different claims.
- **CT logs are historical.** A subdomain in the log may no longer resolve. Check
  before you report it as live.
- **The `Server` header is a lie.** It says `cloudflare`, which describes the
  edge, not the origin server.

## Deliverable

Export the report and answer each question with a citation:

```bash
.venv/bin/osintlab report --case 1 --out mission1.md
```

For every answer, name the source and the retrieval time. If you cannot cite it,
it does not go in the report.

## Extension

Run with `--depth 1` to expand one hop into discovered IPs:

```bash
.venv/bin/osintlab collect example.com --case 1 --depth 1
```

Watch how many entities appear, and how quickly the graph grows. That growth is
why collection needs a scope.
