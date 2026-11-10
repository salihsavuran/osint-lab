# Security policy

## Scope

osint-lab runs locally and holds investigation data, including raw evidence
snapshots. The main security concerns are:

- accidental disclosure of case data,
- SSRF through user-supplied targets,
- dependency vulnerabilities.

## Reporting a vulnerability

Open a private security advisory on GitHub, or email the maintainer listed in
the repository profile. Please do not open a public issue for anything
exploitable.

We aim to respond within seven days.

## Design notes

- The API binds to `127.0.0.1` by default. It has **no authentication** and is
  not intended to be exposed to a network. If you need remote access, put it
  behind a reverse proxy with authentication and TLS.
- All outbound requests go through `osintlab.fetch.Fetcher`. There is no
  user-supplied URL fetching beyond the target a user types in, which is a
  deliberate SSRF surface: a local tool that fetches arbitrary URLs is doing
  what the user asked. Do not run it as a shared service without an allowlist.
- Evidence files are stored under `OSINTLAB_DATA_DIR` with `0600`-equivalent
  filesystem permissions inherited from the directory. Protect that directory.
- No secrets are stored in the repository. `.env` is gitignored.
