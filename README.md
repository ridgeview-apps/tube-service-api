# Tube Service API

A FastAPI service that extends TfL data for the Tube Service mobile app. Its
first feature records line-status snapshots and exposes them by London
calendar day.

## Architecture

There are three deliberately separate parts:

- **API:** serves saved data to the mobile app.
- **Snapshot worker:** polls TfL once every 10 minutes and writes a snapshot only
  when a rail line's status changes. Each snapshot contains its complete
  status list. It covers Tube, Elizabeth line, DLR, London Overground, and
  Trams.
- **Database:** SQLite locally; use PostgreSQL when deployed.

Run the API and snapshot worker as separate processes in production. This prevents
multiple web workers from accidentally polling and saving duplicate data.
The first collection of each London day stores a baseline for every line.
Later collections store only changes, so daily history is a simple date-range
query.

## Prerequisites

- VS Code
- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) for Python and dependency management

The repository contains recommended VS Code extensions and debug
configurations. Open the folder and install the recommended extensions when
prompted.

## Local setup

```bash
uv sync
cp .env.example .env
```

Start the API:

```bash
uv run uvicorn app.main:app --reload
```

All `/v1/line-status/*` endpoints require a configured client key in an
`X-API-Key` request header. Each client has an ID and one or more active random
secrets. Configure them as JSON:

```env
CLIENT_API_KEYS={"ios":["64-character-generated-secret"],"widget":["64-character-generated-secret"]}
```

Generate each client secret separately:

```bash
openssl rand -hex 32
```

Clients send the ID and generated secret joined by a dot, such as
`ios.<generated-secret>`. Multiple secrets can temporarily be configured for
one client during rotation. The `/health` endpoint remains public, and
production traffic must use HTTPS so keys are encrypted in transit.

When `APP_ENV=development`, authentication is disabled if `CLIENT_API_KEYS` is
empty. Configuring keys locally enables authentication, allowing production
behavior to be tested. Every other environment fails closed if no keys are
configured.

In another terminal, start the snapshot worker:

```bash
uv run python -m app.workers.line_status_snapshot_worker
```

Run a single collection for a quick check:

```bash
uv run python -m app.workers.line_status_snapshot_worker --once
```

Open:

- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
- Example timeline:
  <http://127.0.0.1:8000/v1/line-status/timeline?line_id=victoria&date=2026-06-09>

Example authenticated request:

```bash
curl \
  -H "X-API-Key: ios.$IOS_API_KEY" \
  "http://127.0.0.1:8000/v1/line-status/timeline?line_id=victoria"
```

Anonymous TfL requests currently work at a lower rate limit. Add your TfL
`app_key` to `TFL_API_KEY` in `.env` before deploying.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Database

Local development defaults to:

```text
sqlite+aiosqlite:///./tube_service.db
```

For production, provision PostgreSQL and set `DATABASE_URL` in this form:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
```

The app currently creates its table on startup. Before evolving the schema
after launch, add Alembic migrations so deployments can change existing
databases safely.

## Deployment shape

Choose a host that supports:

- A managed PostgreSQL database
- One web service using the Dockerfile's default command
- One continuously running worker using:

```bash
python -m app.workers.line_status_snapshot_worker
```

Set the same `DATABASE_URL` and `TFL_API_KEY` on both services. Set
`CLIENT_API_KEYS` on the web service and distribute the corresponding key to
each authorized client. The API is stateless, so it can later scale
horizontally; keep exactly one snapshot worker instance unless database-level
coordination is added.
