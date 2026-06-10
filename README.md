# Tube Service API

A FastAPI service that extends TfL data for the Tube Service mobile app. Its
first feature records line-status snapshots and exposes them by London
calendar day.

## Architecture

There are three deliberately separate parts:

- **API:** serves saved data to the mobile app.
- **Collector:** polls TfL once every 10 minutes and writes a snapshot only
  when a rail line's status changes. Each snapshot contains its complete
  status list. It covers Tube, Elizabeth line, DLR, London Overground, and
  Trams.
- **Database:** SQLite locally; use PostgreSQL when deployed.

Run the API and collector as separate processes in production. This prevents
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

In another terminal, start the collector:

```bash
uv run python -m app.workers.line_status_collector
```

Run a single collection for a quick check:

```bash
uv run python -m app.workers.line_status_collector --once
```

Open:

- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
- Example history:
  <http://127.0.0.1:8000/v1/line-status/history?line_id=victoria&date=2026-06-09>

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
python -m app.workers.line_status_collector
```

Set the same `DATABASE_URL` and `TFL_API_KEY` on both services. The API is
stateless, so it can later scale horizontally; keep exactly one collector
instance unless database-level coordination is added.
