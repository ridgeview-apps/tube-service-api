# Tube Service API

A FastAPI service that extends TfL data for the Tube Service mobile app. Its
first feature records line-status snapshots and exposes them by London
operational day.

## Architecture

There are four deliberately separate parts:

- **API:** serves saved data to the mobile app.
- **Snapshot worker:** polls TfL once every 15 minutes and writes a snapshot only
  when a rail line's status changes. Each snapshot contains its complete
  status list. It covers Tube, Elizabeth line, DLR, London Overground, and
  Trams.
- **Notification delivery worker:** drains pending push notification deliveries.
  When APNs is configured, it sends iOS pushes; otherwise it uses a no-op sender
  and marks pending deliveries as skipped.
- **Database:** SQLite locally; use PostgreSQL when deployed.

Run the API, snapshot worker, and notification delivery worker as separate
processes in production. This prevents multiple web workers from accidentally
polling and saving duplicate data.
An operational day runs from 04:00 London time to 04:00 the following day.
The first collection of each operational day stores a baseline for every line.
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
uv run alembic upgrade head
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

In another terminal, start the notification delivery worker:

```bash
uv run python -m app.workers.notification_delivery_worker
```

Run a single notification delivery batch:

```bash
uv run python -m app.workers.notification_delivery_worker --once
```

APNs is optional locally. When these variables are present, the notification
delivery worker uses APNs for iOS deliveries:

```env
APNS_TEAM_ID=apple-developer-team-id
APNS_KEY_ID=apple-auth-key-id
APNS_BUNDLE_ID=ios-app-bundle-id
APNS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
APNS_USE_SANDBOX=true
APNS_TEST_PUSH_ENABLED=false
```

`APNS_PRIVATE_KEY` accepts escaped newlines. Do not commit APNs keys, push
tokens, or provider secrets.

A gated test endpoint can send a push to any known iOS notification device:

```bash
curl \
  -X POST \
  -H "X-API-Key: ios.$IOS_API_KEY" \
  "http://127.0.0.1:8000/v1/notification-devices/install-123/test-push"
```

The endpoint returns 404 unless `APNS_TEST_PUSH_ENABLED=true`; it still requires
the normal API key.

Check the latest worker runs:

```bash
curl \
  -H "X-API-Key: ios.$IOS_API_KEY" \
  "http://127.0.0.1:8000/v1/operations/workers"
```

Open:

- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
- Example timeline:
  <http://127.0.0.1:8000/v1/line-status/timeline?line_id=victoria&operational_date=2026-06-09>

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

## Production-like local run

Use Docker Compose to rehearse the deployed process shape with PostgreSQL:

```bash
cp .env.example .env
docker compose up --build
```

Compose starts:

- PostgreSQL
- a one-shot `alembic upgrade head` migration service
- the API at <http://127.0.0.1:8000>
- the line-status snapshot worker
- the notification delivery worker

Stop the stack:

```bash
docker compose down
```

Remove the local PostgreSQL volume:

```bash
docker compose down -v
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

Apply database migrations before starting the API or workers:

```bash
uv run alembic upgrade head
```

Create future migrations after model changes:

```bash
uv run alembic revision --autogenerate -m "Describe the schema change"
uv run alembic upgrade head
```

## Deployment shape

Choose a host that supports:

- A managed PostgreSQL database
- One web service using the Dockerfile's default command
- One continuously running snapshot worker using:

```bash
python -m app.workers.line_status_snapshot_worker
```
- One continuously running notification delivery worker using:

```bash
python -m app.workers.notification_delivery_worker
```

Run migrations before releasing a new version:

```bash
alembic upgrade head
```

The Docker image includes `alembic.ini` and the `migrations/` directory, so the
same image can be used for the web service, workers, and migration command.

Set the same `DATABASE_URL` on all services. Set `TFL_API_KEY` on the snapshot
worker. Set `CLIENT_API_KEYS` on the web service and distribute the corresponding key to
each authorized client. Set the APNs variables on the notification delivery
worker before deploying it. Set `APNS_TEST_PUSH_ENABLED=true` on the API only
while manually verifying push setup, then turn it off again. The API is
stateless, so it can later scale horizontally; keep exactly one snapshot worker
instance unless database-level coordination is added. The notification delivery
worker is idempotent around delivery rows, but run one instance until row-level
claiming is added.

## Railway deployment

The current production deployment uses Railway with:

- One PostgreSQL database service
- One API service built from the Dockerfile
- One snapshot worker service built from the same Dockerfile
- One notification delivery worker service built from the same Dockerfile

API service:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
CLIENT_API_KEYS={"ios":["generated-production-secret"]}
APNS_TEST_PUSH_ENABLED=false
```

The API service uses the Dockerfile default command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Snapshot worker service:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
TFL_API_KEY=generated-tfl-api-key
POLL_INTERVAL_SECONDS=900
```

The snapshot worker start command is:

```bash
python -m app.workers.line_status_snapshot_worker
```

Notification delivery worker service:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
NOTIFICATION_DELIVERY_BATCH_SIZE=100
NOTIFICATION_DELIVERY_POLL_INTERVAL_SECONDS=30
APNS_TEAM_ID=apple-developer-team-id
APNS_KEY_ID=apple-auth-key-id
APNS_BUNDLE_ID=ios-app-bundle-id
APNS_PRIVATE_KEY=escaped-apple-private-key
APNS_USE_SANDBOX=false
```

The notification delivery worker start command is:

```bash
python -m app.workers.notification_delivery_worker
```

Railway deploy settings:

- Enable auto-deploys from GitHub.
- Enable **Wait for CI** on the API and snapshot worker services.
- Run migrations before deployment with:

```bash
alembic upgrade head
```

Do not store production secrets in the repository. Configure them only as
Railway service variables.
