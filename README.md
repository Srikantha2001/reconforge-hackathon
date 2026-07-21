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

- **Frontend:** React + MUI (Vite)
- **Backend:** FastAPI + a pure-function pandas engine
- **LLM:** provider-agnostic and pluggable (`stub` default needs no key; `gemini`
  and `openai`-compatible adapters included)
- **Storage:** Postgres (via docker-compose); the ORM also runs on SQLite for tests

## Quick start

### 1. Configure

```bash
cp .env.example .env      # defaults work out of the box (LLM_PROVIDER=stub)
```

### 2. Start Postgres + backend

```bash
docker compose up -d --build         # db + backend on http://localhost:8000
# API docs: http://localhost:8000/docs
```

The backend seeds a demo ledger/statement pair and a pre-approved fallback
config on first boot, so the app is demoable immediately.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api -> :8000)
```

## Running the backend without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="sqlite+pysqlite:///./data/reconforge.db"   # or a Postgres URL
python -m app.seed.generator --out ./data
uvicorn app.main:app --reload
```

## Tests

```bash
cd backend
pytest -q          # schema+repair, engine matching, reproducibility hash, seed, API
```

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
