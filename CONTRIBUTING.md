# Contributing

Thanks for wanting to help. Two rules matter more than the rest:

1. Read [ETHICS.md](ETHICS.md). A pull request that adds person-profiling,
   breach data or access-control bypass will be closed.
2. Every new collector must declare a **legal basis** and a **rate limit**. The
   registry raises at import time if either is missing.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e 'backend[dev]'
.venv/bin/python -m pytest backend/tests -q
.venv/bin/ruff check backend
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Adding a collector

1. Create `backend/osintlab/collectors/your_source.py`.
2. Subclass `Collector`, set `id`, `label`, `description`, `accepts`,
   `produces`, `legal_basis`, `attribution`, `rate_limit`, `priority`.
3. Implement `collect(ctx) -> CollectorResult`.
4. Call `ctx.get(...)` for every request — never use `httpx` directly. This is
   what gives you caching, rate limiting, retries and evidence capture.
5. Register it in `load_builtin()` in `collectors/base.py`.
6. Add a test with a canned response in `backend/tests/`.

Checklist for the `legal_basis` field:

- Is the endpoint public and unauthenticated?
- Does the operator publish it for programmatic access?
- Is the data about infrastructure or organisations rather than private people?

If any answer is "no", the collector does not belong here.

## Style

- Python: `ruff` with the repo config. Type hints everywhere.
- Frontend: Svelte 5 runes, no TypeScript required.
- Comments explain *why*, not *what*. The existing code is the reference.

## Tests

Tests must not touch the network. Use `FakeFetcher` from `conftest.py` with a
canned response. If you need a real fixture, capture it once and commit the
JSON under `backend/tests/fixtures/`.
