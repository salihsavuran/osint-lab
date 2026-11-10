# Mission 2 — Trace a corporate identity

**Goal:** establish which legal entity you are actually looking at, and prove it.

**Target:** a well-known public company of your choice. Pick one with an SEC
filing so EDGAR has something to return.

**Time:** 25 minutes.

## Setup

```bash
.venv/bin/osintlab case create \
  --title "Mission 2: corporate identity" \
  --scope "Public company, public filings, legitimate research"
.venv/bin/osintlab collect "Apple Inc" --case 2
```

## Questions to answer

1. What is the company's CIK, and what industry code does the SEC assign it?
2. What is its LEI, and in which jurisdiction is it registered?
3. Has it changed its name? When, and from what?
4. Does its name appear on any sanctions list? If so, is that the same entity?
5. What does Wikidata claim about it, and does that match the filings?

## The core lesson

Three sources, three different notions of "the same company":

| Source | Identity key | Authoritative for |
| --- | --- | --- |
| EDGAR | CIK | US securities filings |
| GLEIF | LEI | Legal identity, globally |
| Wikidata | QID | Nothing in particular |

A CIK and an LEI describe the *same* legal person only if you can show the
mapping. Do not assume it. This is the entity-resolution problem, and it is
where most OSINT reports go wrong.

## What to notice

- **Name matching is not identity.** The `ofac` collector reports matches as
  leads. A common company name will produce false positives. Check the program,
  the country and any identifiers before drawing a conclusion.
- **Former names are a pivot.** EDGAR's `formerNames` often explains why a
  search returned nothing.
- **Wikidata is convenient and unreliable.** It will give you a tidy answer
  immediately. Check it against the primary filing.

## Deliverable

Write a short paragraph identifying the entity, citing at least two independent
sources for the identity claim, and explicitly stating which sources you could
not reconcile.
