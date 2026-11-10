# Ethics and acceptable use

osint-lab is a teaching tool. It exists so people can learn how open-source
intelligence actually works — including its limits — without building the
machinery for harassing someone.

## The line we draw

**In scope:** infrastructure and organisations.

- domains, subdomains, IP addresses, prefixes, ASNs
- TLS certificates published to Certificate Transparency logs
- corporate registrations, filings, legal entity identifiers
- sanctions and watchlists published by governments

**Out of scope:** building a profile on a private individual.

- no email or home-address discovery
- no reverse phone lookup that identifies a subscriber (see [Phone numbers](#phone-numbers))
- no social-media aggregation or "find all accounts for this person"
- no breach or leaked-credential data
- no facial recognition or image-based identification
- no automated tracking of a person's location or movements

A person's name may appear in this tool only as an officer or director attached
to a public corporate filing. Nothing enriches it, and nothing pivots from it to
contact details.

## Why the line sits there

Infrastructure and corporate registries are published *for* public consumption.
A domain's registration record exists specifically so anyone can look it up. An
ASN holder is public routing data by design.

A private individual's contact details, daily location and social graph are not
published for that purpose. Assembling them into a dossier is the definition of
doxxing, regardless of whether each individual piece is technically public. The
harm comes from the aggregation, not the individual records.

Teaching the first category is education. Building the second is a weapon.

## Phone numbers

A phone number sits on the line, so the rule is stated explicitly.

**Allowed — describing the number:**

- Is it a valid number within its numbering plan?
- Which country and region is the range allocated to?
- Is it a mobile, fixed line, VoIP, toll-free or premium range?
- Which operator was the range originally allocated to?
- Which timezones does the range span?

This is public numbering-plan data. It is what your phone's dialer uses to
format a number correctly, and it reveals nothing about a person.

**Not allowed — identifying the subscriber:**

- Reverse lookup to a name
- HLR / home-location-register probes that test whether a number is live
- "Who called me" style databases built from scraped or leaked data
- Linking a number to social accounts, addresses or other identifiers
- Bulk enumeration of a range to find active numbers

The first list describes a **number**. The second list describes a **person**,
and a number is one of the strongest join keys between datasets. That is why the
line is drawn there rather than at "is the data public".

## Rules the code enforces

These are not suggestions — they are implemented.

1. **Public, documented interfaces only.** No scraping behind authentication, no
   bypassing paywalls or access controls.
2. **Declared legal basis.** A collector cannot be registered without stating
   the legal basis for reading its source.
3. **Published rate limits.** Every collector declares its source's limit and
   the runner enforces it with a sliding window.
4. **Identifying User-Agent.** Requests identify the tool and, ideally, a
   contact address.
5. **Evidence retention.** Raw responses are stored and hashed, so claims can be
   checked rather than trusted.
6. **Audit log.** Every collection run records the target, the collectors and
   the time.

## Rules for users

- **Only collect on targets you are authorised to assess.** Your own domains,
  your organisation's assets, documentation domains such as `example.com`, or
  organisations you are legitimately researching.
- **Do not use this to investigate a private person.** Even if you are curious,
  even if the data is "public".
- **Verify before you publish.** A name match on a sanctions list is a lead, not
  a finding. `ofac` says so in its own output.
- **Respect the law where you are.** GDPR, the CFAA, the UK Computer Misuse Act
  and similar statutes apply to collection, not just to hacking.
- **Record your scope.** The `--scope` flag on a case is not decoration; it is
  what makes your work defensible.

## If you are a teacher

Use `OSINTLAB_OFFLINE=true` with a pre-populated cache, or the exercises in
`docs/missions/`, so students never send live traffic to a third party without
understanding what they are doing.

## Reporting a concern

If you believe this project has a feature that crosses the line above, open an
issue or email the maintainer. We would rather remove a collector than ship
something that causes harm.
