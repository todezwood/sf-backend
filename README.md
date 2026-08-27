# Contacts Backend

A self-contained Contacts REST API built with **FastAPI** + **SQLAlchemy**, backed by an
**in-memory SQLite database** by default. No external database, container, or migration
step is needed — start the process and the API is ready.

## Quickstart

```bash
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -r requirements.txt
.venv/bin/python -m app.main
```

Then open <http://127.0.0.1:8000/docs> for interactive Swagger UI.

Alternatively, with uvicorn directly (adds `--reload`):

```bash
.venv/bin/uvicorn app.main:app --reload
```

## Interactive API docs

FastAPI generates an OpenAPI schema from the route signatures and Pydantic models, so
the docs are never out of date with the code. With the server running, three URLs are
served:

| URL | What it is |
| --- | --- |
| <http://127.0.0.1:8000/docs> | **Swagger UI** — browse endpoints and send real requests from the browser |
| <http://127.0.0.1:8000/redoc> | **ReDoc** — read-only reference, easier for reading schemas end to end |
| <http://127.0.0.1:8000/openapi.json> | Raw OpenAPI 3.1 schema, for client generators and Postman/Insomnia imports |

If you changed `CONTACTS_HOST` or `CONTACTS_PORT`, substitute those instead.

### Trying a request in Swagger UI

1. Expand an endpoint, e.g. `POST /api/v1/contacts`.
2. Click **Try it out** — the request body becomes editable and is pre-filled with an
   example.
3. Edit the JSON and click **Execute**.
4. The response status, body, and headers appear below, along with the equivalent
   `curl` command you can copy.

Since the default database is seeded on startup, `GET /api/v1/contacts` returns three
contacts immediately — a good first call to confirm things work. Anything you create
through the UI lives only until the process exits.

### Reading the schemas

Both UIs list every model under **Schemas** (ReDoc) or **Schemas** at the bottom of the
page (Swagger UI). `ContactCreate`, `ContactReplace` (PUT), `ContactUpdate` (PATCH),
`ContactRead`, and `ContactPage` show exactly which fields are required, which are
nullable, and the validation rules — the same constraints described in
[Contact fields](#contact-fields) below. Endpoints are grouped
by the tags declared in `app/main.py`, and each documents its error responses (`404`,
`409`, `422`) with example payloads.

Neither UI requires the docs to be enabled explicitly; to turn them off in a deployment,
pass `docs_url=None` / `redoc_url=None` to `FastAPI(...)` in `app/main.py`.

## The in-memory database

`CONTACTS_DATABASE_URL` defaults to `sqlite+pysqlite:///:memory:`. A plain in-memory
SQLite database normally dies with the connection that opened it, so `app/database.py`
uses SQLAlchemy's `StaticPool` to hold one connection open for the process's lifetime.
Every request — including ones FastAPI runs on a worker thread — sees the same data.

**Data is lost when the process exits.** Because of that, three sample contacts are
seeded on startup so the API is never empty. To persist instead, point at a file:

```bash
CONTACTS_DATABASE_URL="sqlite+pysqlite:///./contacts.db" .venv/bin/python -m app.main
```

The same code runs unchanged against Postgres (`postgresql+psycopg://...`).

### Configuration

All settings are environment variables prefixed with `CONTACTS_` (a `.env` file is
also read):

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTACTS_DATABASE_URL` | `sqlite+pysqlite:///:memory:` | SQLAlchemy URL |
| `CONTACTS_SEED_DATA` | `true` | Insert sample contacts if the DB is empty |
| `CONTACTS_HOST` | `127.0.0.1` | Bind address |
| `CONTACTS_PORT` | `8000` | Bind port |
| `CONTACTS_SQL_ECHO` | `false` | Log every SQL statement |

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness + database check and contact count |
| `GET` | `/` | Entry-point listing |
| `POST` | `/api/v1/contacts` | Create a contact → `201` |
| `GET` | `/api/v1/contacts` | List with search, sort, pagination |
| `GET` | `/api/v1/contacts/{id}` | Fetch one contact |
| `PUT` | `/api/v1/contacts/{id}` | Full replace (omitted fields are cleared) |
| `PATCH` | `/api/v1/contacts/{id}` | Partial update (only sent fields change) |
| `DELETE` | `/api/v1/contacts/{id}` | Delete → `204` |

### Contact fields

`first_name` and `last_name` are required; `email` is required and unique
(case-insensitive). Everything else is optional.

```
first_name, last_name, email, phone, company, job_title,
address, city, state, postal_code, country, notes
```

Responses add `id`, `full_name`, `created_at`, and `updated_at` (UTC).

### List query parameters

| Param | Default | Notes |
| --- | --- | --- |
| `search` | – | Case-insensitive substring match on name, email, company, phone |
| `limit` | `50` | 1–200 |
| `offset` | `0` | |
| `sort_by` | `id` | `id`, `first_name`, `last_name`, `email`, `company`, `created_at`, `updated_at` |
| `order` | `asc` | `asc` or `desc` |

List responses are wrapped so clients can paginate:

```json
{ "items": [ ... ], "total": 12, "limit": 50, "offset": 0 }
```

### Status codes

`201` created · `204` deleted · `404` unknown id · `409` duplicate email ·
`422` validation error (bad email, blank name, invalid `sort_by`)

## Examples

```bash
# Create
curl -X POST http://127.0.0.1:8000/api/v1/contacts \
  -H 'content-type: application/json' \
  -d '{"first_name":"Katherine","last_name":"Johnson","email":"katherine@example.com",
       "phone":"+1-757-555-0199","company":"NASA","job_title":"Mathematician"}'

# Search + paginate
curl "http://127.0.0.1:8000/api/v1/contacts?search=nasa&limit=10&sort_by=last_name"

# Partial update
curl -X PATCH http://127.0.0.1:8000/api/v1/contacts/1 \
  -H 'content-type: application/json' -d '{"phone":"+1-415-555-0000"}'

# Delete
curl -X DELETE http://127.0.0.1:8000/api/v1/contacts/1
```

## Tests

```bash
.venv/bin/python -m pytest
```

Tests run against their own empty in-memory database with seeding disabled
(see `tests/conftest.py`).

## Layout

```
app/
  main.py             FastAPI app, lifespan startup, /health and /
  config.py           Environment-driven settings
  database.py         Engine, session factory, StaticPool in-memory wiring
  models.py           Contact ORM model
  schemas.py          Pydantic request/response models
  crud.py             Database operations (search, sort, paginate)
  seed.py             Sample contacts for the in-memory default
  routers/contacts.py REST endpoints
tests/                API tests via FastAPI TestClient
```

<!-- Qodo pipeline check -->
