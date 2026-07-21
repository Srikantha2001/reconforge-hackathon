# ReconForge

> Author any reconciliation from natural language in minutes, run it with
> control-grade determinism, and resolve breaks with agents that explain
> themselves, refuse to guess, and get smarter from every human action.

**The core law:** the LLM *authors configuration (rules) at design-time* and
*advises on breaks post-run*. It **never** matches transactions — matching is
done only by a deterministic Python engine. This buys auditability (a versioned
rule is explainable), determinism (same input → identical output hash), and cost
(author a rule once, not one inference per transaction).

## Architecture (four planes)

| Plane | What happens |
|---|---|
| **Design-time** | NL + 2 CSVs → LLM → schema-validated config JSON → **human approval gate** → versioned persist |
| **Run-time** | Deterministic engine: transforms → key match → rule eval → matched pairs + breaks; reproducibility hash |
| **Resolution** | SME agent classifies each break (1 of 10 archetypes) → Judge agent (accept / route-to-human); chaser draft (never auto-sent) |
| **Learning** | Loop A: manual matches → aggregated deltas → proposed config change → **human approval** → new version. Loop B: resolution memory (retrieve similar → few-shot / short-circuit) |

Both entry points into the versioned config (initial authoring, Loop A
refinement) pass through the **same human maker-checker gate** — the maker cannot
self-approve.

## Stack

- **Frontend:** React + MUI (Vite), TypeScript
- **Backend:** FastAPI + a pure-function pandas engine, SQLAlchemy
- **LLM:** provider-agnostic and pluggable (`stub` default needs no key; `gemini`
  and `openai`-compatible adapters included)
- **Storage:** Postgres (via docker-compose); the ORM also runs on SQLite for tests
- **Deploy (local):** Docker Compose for Postgres + backend; Vite dev server for the frontend

---

## Prerequisites

| Tool | Verified version | Notes |
|---|---|---|
| **Docker Desktop** (with Compose v2) | Docker 29.x, Compose v5.x | Needed for the Postgres + backend path. Must be *running* before `docker compose up`. |
| **Node.js** | v20+ (verified on v26.5.0) | Needed for the frontend. `npm` ships with it. |
| **Python** | 3.11+ for the Docker image; 3.9+ works for running the backend directly on the host (verified on 3.9.6) | Only needed if you want to run the backend without Docker, or run the test suite locally. |

macOS note: if `node`/`npm` aren't installed, `brew install node` gets you the
versions above. If Docker Desktop is installed but not running, `open -a Docker`
starts it (wait a few seconds, then `docker info` should succeed).

You do **not** need an LLM API key to run anything — the default
`LLM_PROVIDER=stub` is a deterministic, fully-offline implementation of every
LLM-shaped step (authoring, summarizing, break explanations, Loop A proposals).
It's also what the reproducibility tests rely on.

---

## Local setup — recommended path (Docker Compose + Vite)

This is the path actually exercised end-to-end for this project: Postgres and
the backend run in Docker, the frontend runs on the host via Vite (fast
hot-reload, and it proxies `/api` to the backend so there's no CORS to think
about).

### 1. Clone / open the repo and configure environment

```bash
cd /path/to/hackathon
cp .env.example .env      # defaults work out of the box (LLM_PROVIDER=stub)
```

All configuration lives in this one `.env` file (see [Configuration
reference](#configuration-reference) below). You almost never need to change
anything for a local run.

### 2. Start Postgres + backend

```bash
docker compose up -d --build
```

What this does:
- Builds the backend image on **Python 3.11-slim**, installs `backend/requirements.txt`.
- Starts a `postgres:16-alpine` container and waits for its healthcheck.
- Generates the seed data (`ledger.csv` / `statement.csv` + a pre-approved
  fallback config) **at image build time**, so the app has a rehearsed pair
  ready immediately — this is also the self-check that guarantees all 10 break
  archetypes + the 3-day drift cluster are present (build fails loudly if not).
- Starts the FastAPI backend on **http://localhost:8000**.

Verify both containers are up and healthy:

```bash
docker compose ps
# NAME                 STATUS
# reconforge-backend   Up
# reconforge-db        Up (healthy)

curl -s http://localhost:8000/api/health
# {"status":"ok","llm_provider":"stub"}
```

If something looks wrong, tail the logs:

```bash
docker compose logs backend --tail 50
docker compose logs db --tail 50
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

This starts Vite on **http://localhost:5173**. Open that URL in a browser.
`vite.config.ts` proxies any `/api/*` request to `http://localhost:8000`, so
the frontend and backend can be developed independently without CORS
configuration getting in the way.

### 4. Walk through the app

Open **http://localhost:5173**. The UI is a 5-step flow:

1. **Configure** — type a description (a sensible default is pre-filled), click
   **Author config**. The LLM (stub, by default) authors a schema-validated
   config against the seed CSV's real column headers; review the generated
   rules and English summary, then **Approve** — note the app will refuse to
   let the same "acting as" actor both author and approve (switch the actor
   in the top-right selector to approve).
2. **Run** — toggle "use rehearsed seeded pair" (on by default) or upload your
   own two CSVs, then **Run reconciliation**. You'll see the match rate, a
   split matched/unmatched bar, and the output hash. Click **Verify
   reproducibility** to re-run the engine on the same inputs and confirm the
   hash matches — the control, not a guess.
3. **Breaks** — inspect any break: row-by-row diff, deterministic archetype +
   explanation, **Advise** (runs the SME + Judge agents), **Draft chaser**
   (read-only, never sent), **Manual match** (feeds Loop A), **Resolve** (feeds
   Loop B / resolution memory).
4. **Learning loops** — after manually matching a few of the drift-cluster
   breaks (`DRF0001`–`DRF0005`, which disagree only on value date by exactly 3
   days), this page aggregates the pattern and lets you **Propose a config
   change** (widening the date tolerance), **Preview what-if** (shows the
   projected match-rate jump *before* approving), then **Approve & re-run**
   through the same maker-checker gate.
5. **Audit log** — every action: actor, agent confidence, before/after state,
   and agent reasoning.

---

## Local setup — without Docker (backend on the host)

Useful for backend development/debugging without rebuilding the Docker image
each time.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Pick a database. Either point at the Postgres container (start it alone with
`docker compose up -d db` from the repo root), or use SQLite for a
zero-dependency local run:

```bash
# Option A: SQLite (simplest, no Postgres needed)
export DATABASE_URL="sqlite+pysqlite:///./data/reconforge.db"

# Option B: Postgres (e.g. the docker-compose db, started separately)
export DATABASE_URL="postgresql+psycopg2://reconforge:reconforge@localhost:5432/reconforge"
```

Generate the seed data (idempotent — safe to re-run):

```bash
python -m app.seed.generator --out ./data
# Seed written to data: 75 ledger rows, 75 statement rows.
# All 10 break archetypes + 3-day drift cluster verified present.
```

Start the API with auto-reload:

```bash
uvicorn app.main:app --reload
# http://localhost:8000, docs at http://localhost:8000/docs
```

Then start the frontend exactly as in step 3 above (`cd frontend && npm install && npm run dev`).

> **macOS + Python 3.9 note:** if `pip install -r requirements.txt` fails
> building `psycopg2-binary`, it's almost always a missing prebuilt wheel for
> your exact Python/arch combo. `requirements.txt` is already pinned to a
> version (`2.9.12`) verified to have wheels for Python 3.9 on macOS arm64; if
> you hit this on a different platform, bump the psycopg2-binary version or run
> `pip install --only-binary :all: psycopg2-binary` to see what's available.

---

## Verifying everything works (no UI needed)

A scripted smoke test of the whole CORE + Loops flow, using `curl`:

```bash
# 1. Health + actors
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/actors

# 2. Seed data is present
curl -s http://localhost:8000/api/seed/info

# 3. Author a config (as alice)
curl -s -X POST http://localhost:8000/api/configs/author \
  -H "Content-Type: application/json" \
  -d '{
    "nl_description": "Match ledger to statement exactly on trade id, amount tolerance of 0.01, within 2 days for value date, and account must match exactly",
    "actor_id": "alice",
    "columns_a": ["trade_id","amount","ccy","value_date","account","counterparty"],
    "columns_b": ["ref","amount","ccy","value_date","account","description"]
  }'
# -> note the returned "id"

# 4. Approve as bob (a maker cannot self-approve)
curl -s -X POST http://localhost:8000/api/configs/<id>/approve \
  -H "Content-Type: application/json" -d '{"actor_id": "bob"}'

# 5. Run on the seeded pair
curl -s -X POST http://localhost:8000/api/runs \
  -F "config_id=<id>" -F "actor_id=alice" -F "use_seed=true"
# -> note the returned run "id"

# 6. Reproducibility check
curl -s -X POST http://localhost:8000/api/runs/<run_id>/reproducibility-check
# -> {"reproducible": true, ...}
```

Full interactive API docs (Swagger UI) are always available at
**http://localhost:8000/docs** while the backend is running.

---

## Running tests

### Backend (pytest)

```bash
cd backend
pip install -r requirements.txt   # if not already installed
pytest -q
# 44 passed
```

Covers: config schema validation + deterministic repair-on-fail, the
deterministic engine (matching, transforms, archetype classification,
reproducibility hash equality), the seed generator (all 10 archetypes + drift
cluster present, reproducible), and a full sequential API workflow test
(author → approve gate → run → advise → manual match → Loop A propose/what-if/
approve → re-run → Loop B resolve → audit trail). Tests use an isolated SQLite
file (`backend/tests/test_reconforge.db`, recreated each session) and the
`stub` LLM provider — no network or API key required.

### Frontend (typecheck + build)

```bash
cd frontend
npm install    # if not already installed
npm run build  # tsc -b && vite build
```

A clean build (`tsc -b`) is the frontend's correctness check — there is no
separate frontend test suite in this build.

---

## Configuration reference

Everything is centralized in `.env` (copy from `.env.example`). Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://reconforge:reconforge@localhost:5432/reconforge` | Full SQLAlchemy URL; overrides the `POSTGRES_*` parts below if set. Use a `sqlite+pysqlite:///...` URL for a zero-dependency local run. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` / `POSTGRES_PORT` | `reconforge` / `reconforge` / `reconforge` / `localhost` / `5432` | Used by docker-compose to configure the Postgres container. |
| `LLM_PROVIDER` | `stub` | `stub` (deterministic, offline), `gemini` (needs `GEMINI_API_KEY`), or `openai` (needs `OPENAI_API_KEY`, optionally `OPENAI_BASE_URL` for any OpenAI-compatible gateway). Falls back to `stub` automatically if the required key is missing or the provider errors. |
| `LLM_MODEL` | *(unset → provider default)* | Optional model name override, e.g. `gemini-1.5-flash` or `gpt-4o-mini`. |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` | *(empty)* | Only needed if you switch `LLM_PROVIDER` away from `stub`. |
| `STP_THRESHOLD` | `0.90` | Autonomy dial: Judge confidence ≥ threshold auto-accepts a break; below it, routes to a human. |
| `UPLOAD_DIR` | `./uploads` | Where uploaded CSV pairs are stored (path recorded on the `run` row). |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin for the backend (only relevant if you bypass the Vite proxy). |

To try a real LLM provider instead of the stub:

```bash
# in .env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
# then:
docker compose up -d --build backend   # or restart uvicorn if running on the host
```

Every LLM output (config authoring, Loop A proposals) is still validated
against the frozen schema with repair-on-fail before it's trusted — switching
providers never bypasses that gate.

---

## Stopping / cleaning up

```bash
docker compose down          # stop Postgres + backend containers
docker compose down -v       # also delete the Postgres data volume (full reset)
```

The frontend dev server stops with `Ctrl+C` in its terminal (or via whatever
process manager started it).

---

## Project structure

```
.
├── .env.example              # centralized config template (copy to .env)
├── docker-compose.yml        # Postgres + backend, for local Docker runs
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI app, CORS, router wiring
│       ├── config.py         # centralized Settings (reads .env)
│       ├── config_schema.py  # frozen JSON Schema + repair-on-fail validator
│       ├── models.py         # six-table SQLAlchemy model
│       ├── db.py             # engine/session setup (Postgres or SQLite)
│       ├── actors.py         # seeded maker-checker identities
│       ├── services.py       # orchestration: runs, advise, Loop A/B, audit
│       ├── engine/           # pure deterministic matching engine
│       │   ├── runner.py     # transforms -> key match -> rule eval -> hash
│       │   ├── matching.py   # rule evaluation (exact/tolerance types)
│       │   ├── archetype.py  # deterministic break classifier (no-LLM fallback)
│       │   ├── transforms.py
│       │   └── hashing.py    # canonical reproducibility hash
│       ├── llm/               # pluggable LLM provider interface
│       │   ├── base.py       # abstract interface
│       │   ├── stub.py       # deterministic, no-key default
│       │   ├── gemini.py
│       │   └── openai_compat.py
│       ├── seed/generator.py # seed data with all 10 archetypes + drift cluster
│       └── routers/          # FastAPI route modules (configs, runs, breaks, loops, audit, ...)
├── frontend/
│   └── src/
│       ├── App.tsx           # stepper orchestrating the 5-step flow
│       ├── api.ts            # typed fetch client for the backend
│       ├── theme.ts          # MUI theme (design system)
│       ├── context/ActorContext.tsx
│       ├── components/       # VersionChip, SplitMatchedBar, DoubleRuleTotal, ...
│       └── pages/             # ConfigureStep, RunStep, BreaksStep, LoopAStep, AuditStep
└── README.md
```

---

## The frozen config contract

```json
{
  "recon_name": "Nostro_USD_Daily",
  "source_a": { "alias": "ledger", "key_columns": ["trade_id"] },
  "source_b": { "alias": "statement", "key_columns": ["ref"] },
  "transforms": [{ "field": "amount", "op": "abs" }, { "field": "ccy", "op": "upper" }],
  "match_rules": [
    { "field_a": "trade_id", "field_b": "ref", "type": "exact" },
    { "field_a": "amount", "field_b": "amount", "type": "numeric_tolerance", "tolerance": 0.01 },
    { "field_a": "value_date", "field_b": "value_date", "type": "date_tolerance", "tolerance_days": 2 }
  ]
}
```

- **Match types:** `exact`, `numeric_tolerance` (needs `tolerance`), `date_tolerance` (needs `tolerance_days`)
- **Transform ops:** `abs`, `upper`, `lower`, `strip`, `round2` (optional `side`: `a` | `b` | `both`)
- Every LLM output is validated against this schema with deterministic
  **repair-on-fail**, then hard-fails if still invalid.

## The 10 break archetypes

value-date mismatch · FX rounding · partial fill · duplicate entry · fee/charge
difference · timing/settlement lag · wrong account/reference · missing
counterparty leg · amount outside tolerance · reference/ID format mismatch.

The seed data contains at least one of each plus a 3-day settlement-drift cluster
so Loop A has a systemic signal to discover.
