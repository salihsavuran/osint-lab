# Deployment

osint-lab is a single-user, local tool. The recommended deployment is a virtual
environment on your own machine. Everything else here is optional.

## Local (recommended)

```bash
git clone https://github.com/salihsavuran/osint-lab.git
cd osint-lab
python3 -m venv .venv
.venv/bin/pip install -e 'backend[dev]'
.venv/bin/osintlab init
.venv/bin/osintlab serve
```

Open <http://127.0.0.1:8000>. The API docs are at `/docs`.

Data lives in `~/.local/share/osint-lab/`:

```
osintlab.db          SQLite database
evidence/<sha>.bin   raw source responses, content-addressed
```

To keep data with the project instead, set `OSINTLAB_DATA_DIR=./data` in `.env`.

## Web UI, two ways

**Development** — two processes, hot reload:

```bash
.venv/bin/osintlab serve            # :8000
cd frontend && npm install && npm run dev   # :5173, proxies /api
```

**Single process** — build once, serve from FastAPI:

```bash
cd frontend && npm install && npm run build && cd ..
.venv/bin/osintlab serve
```

FastAPI mounts `frontend/build` at `/` when it exists.

## Postgres

SQLite is fine for one user. For Postgres:

```bash
pip install 'psycopg[binary]'
export OSINTLAB_DATABASE_URL='postgresql+psycopg://user:pass@localhost/osintlab'
.venv/bin/osintlab init
```

The schema uses no SQLite-specific features. `JSON` columns are stored as text,
so no migration is needed.

## Docker

Not required, and not the primary path. A minimal compose file is included for
convenience:

```bash
docker compose up --build
```

## Classroom / offline

The most reproducible setup for teaching:

1. Pre-populate a cache on a machine with network access.
2. Copy `OSINTLAB_DATA_DIR` to the classroom machines.
3. Set `OSINTLAB_OFFLINE=true`.

In offline mode the fetcher refuses to open a socket and serves cached responses
only, so students cannot accidentally send live traffic to a third party.

```bash
export OSINTLAB_OFFLINE=true
.venv/bin/osintlab collect example.com --case 1   # replays the cache
```

## Hardening

The API has **no authentication** and binds to `127.0.0.1`. Do not expose it to
a network as-is. If you must, put it behind a reverse proxy with authentication
and TLS, and restrict the targets users can enter.

## Backups

Two things matter: the database and the evidence directory. Copy both together —
a database without its evidence is a set of unciteable claims.

```bash
tar czf osint-lab-backup-$(date +%F).tar.gz \
  -C ~/.local/share osint-lab
```
