# Mission 3 — Verify a claim across independent sources

**Goal:** learn to distinguish "a source said it" from "it is true".

**Time:** 30 minutes.

## The setup

Pick a factual claim about a domain or organisation that you can check. Examples:

- "This domain has been registered since 1995."
- "This company is headquartered in California."
- "This site has been online continuously since 2001."
- "This organisation is not under sanctions."

## The method

For each claim, fill in this table before you write anything:

| Claim | Source 1 | Source 2 | Agree? | Independent? |
| --- | --- | --- | --- | --- |
| | | | | |

Two questions matter more than the answer:

1. **Are the sources actually independent?** Wikidata citing the company's own
   website is one source, not two. A registrar and a registry are different
   organisations; a registrar and its own WHOIS mirror are not.
2. **What would falsify the claim?** If nothing could, you are not verifying,
   you are confirming.

## Worked example

Claim: *"example.com has been registered since 1995."*

- **RDAP** (`rdap.event.registration`) → `1995-08-14`. Primary, authoritative.
- **Wayback** (`archive.first_snapshot`) → `2002-01-20`. Independent, but
  measures *archiving*, not registration.

They do not contradict: the domain existed seven years before the Archive
crawled it. A careless analyst would report "first seen 2002" as the creation
date. The lesson is that each source measures a different thing, and the
attribute name tells you which.

## Failure modes to hunt for

- **Circular citation.** Two sources that copy each other.
- **Proxy metrics.** Archive date presented as creation date; ASN holder
  presented as owner; server header presented as origin technology.
- **Stale data.** Cache TTLs exist for a reason. Check `retrieved_at`.
- **Absence of evidence.** "No sanctions match" is not "not sanctioned". The
  list may be incomplete, the name may be transliterated differently, or the
  match threshold may have missed it.

## Deliverable

For your chosen claim, write:

1. The claim, stated precisely.
2. Each source, what it actually measures, and its retrieval time.
3. Whether the sources are independent.
4. Your confidence, and what would change it.

Then run:

```bash
.venv/bin/osintlab report --case <id> --out mission3.md
```

Check that every row in your table appears in the report with a citation. If it
does not, your evidence is not in the tool — and therefore not in your report.
