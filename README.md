# ReconOS

> Deutsche Bank Securities Services' AI-native reconciliation fabric —
> deterministic matching, regulatory automation, and client-facing intelligence.

**The core law:** the LLM *authors configuration at design-time* and *advises on
breaks post-run*. It **never** matches transactions — matching is done only by a
deterministic Python/pandas engine. Same input → identical SHA-256 output hash,
every run. That is a financial control, not a software feature.

## Architecture — four planes

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │ DESIGN-TIME   NL description ──▶ LLM ──▶ schema-validated config JSON │
 │               (repair-on-fail is deterministic; maker ─▶ checker gate)│
 ├───────────────────────────────────────────────────────────────────────┤
 │ RUN-TIME      transforms ─▶ position proof ─▶ 7-pass matching         │
 │               waterfall (exact → date-tol → qty-round → fx-round →    │
 │               1:N → N:1 → N:M subset-sum) ─▶ breaks ─▶ SHA-256 hash   │
 ├───────────────────────────────────────────────────────────────────────┤
 │ RESOLUTION    SME classifier (12 archetypes, 9 causal origins,        │
 │               3-layer root-cause tree) ─▶ Judge routing bands:        │
 │               <0.65 senior · <0.90 maker · ≥0.90 STP · regulatory     │
 │               always escalates ─▶ maker-checker governance ─▶         │
 │               export-only journal entries                             │
 ├───────────────────────────────────────────────────────────────────────┤
 │ LEARNING      Loop A: 4+ force-matches with one systemic drift ─▶     │
 │               proposed config re-version (DATE_TOLERANCE capped at 5d,│
 │               what-if preview, checker approves, old vers. SUPERSEDED)│
 │               Loop B: resolution memory recalled as few-shot          │
 └───────────────────────────────────────────────────────────────────────┘
```

Regulatory rides on top: **EMIR Article 15** (breaks > €15M unresolved > 15
business days → draft notification, human-filed), **CASS 7A** (daily client-money
safeguarding recon with hashed resolution packs), CSDR (placeholder). A **client
portal** lets a fund upload its own positions, reconcile against the bank's
books, and download a hash-stamped evidence pack.

## Stack

- **Backend:** Python 3.11 (Docker) / 3.9+ (host), FastAPI, pandas, SQLAlchemy, **SQLite**
- **Frontend:** React 18 + TypeScript + Vite + MUI
- **Auth:** JWT (PyJWT + bcrypt), five seeded demo roles
- **LLM:** pluggable — `stub` (default, deterministic, fully offline), `gemini`, `openai`-compatible

No API key is needed for anything: `LLM_PROVIDER=stub` implements every
LLM-shaped step deterministically, which is also what the reproducibility tests
rely on.

## Quick start

```bash
git clone <repo> && cd hackathon
```
```bash
cp .env.example .env
```
```bash
docker compose up -d --build
```
```bash
npm --prefix frontend install
```
```bash
npm --prefix frontend run dev
```

Open **http://localhost:5173**. The backend is at http://localhost:8000
(interactive API docs: **http://localhost:8000/docs**). Optionally add a
`GEMINI_API_KEY` + `LLM_PROVIDER=gemini` to `.env` for live LLM prose — nothing
else changes.

## Demo users

| Email | Password | Role |
|---|---|---|
| `maker@db.com` | `maker123` | MAKER |
| `checker@db.com` | `checker123` | CHECKER |
| `admin@db.com` | `admin123` | ADMIN |
| `client@alphacapital.com` | `client123` | CLIENT |
| `dsi@db.com` | `dsi123` | DSI |

## Demo walkthrough (8 steps)

The seeded dataset is 25 IBOR positions vs 21 BNY Mellon custody records,
engineered so every waterfall pass and break archetype fires.

1. **Sign in as maker** (`maker@db.com`) → Configure → **Author new config** →
   **Submit for approval**. (Offline authoring instantiates the pre-approved
   securities recon; every config is schema-validated with deterministic repair.)
2. **Sign in as checker** → Configure → **Approve**. The maker cannot
   self-approve — enforced at the API *and* by a DB constraint.
3. As **maker**, Dashboard → **Execute on seed**: 14 matched across 7 passes
   (5·2·1·1·1·2·2), 9 open breaks, position proof **PROVED**
   (2,747,000 + 250,300 = 2,997,300, variance 0), 1 regulatory flag.
4. Run & breaks → **Analyze breaks (SME + Judge)**: every break gets an
   archetype, causal origin, and a 3-layer root-cause tree. TRD022 (a €16.5M
   valuation dispute, 300k delta) routes to **Regulatory escalation** regardless
   of confidence; the missing leg escalates to a senior; the drift cluster goes
   to maker review.
5. **Force-match the four drift breaks** (TRD008–011) from the break drilldown;
   approve each as checker in Governance. Each approval writes an export-only
   journal entry with a SHA-256 audit reference — never auto-posted.
6. Learning → **Loop A detects** "4× settlement-date drift of 3 days" →
   **Propose config change** → what-if preview shows the candidate match rate
   improving with zero newly-broken keys → checker approves → v1.1.0 is born and
   v1.0.0 is SUPERSEDED. (The proposal engine caps DATE_TOLERANCE at 5 days.)
7. As **checker**, Regulatory: the EMIR tab holds the drafted Article-15
   notification (approve → FILED, audited); the CASS tab shows the ACC002
   €5,000 shortfall with a downloadable, hash-stamped resolution pack. As
   **client**, upload a position CSV in the portal → simplified results →
   evidence pack with a stable `document_hash`.
8. **The moment that matters:** back on the Dashboard, click **Reproduce**.
   Watch the SHA-256 match: *"Same input, same output, every time. Not because
   we got lucky — because the engine has no randomness. That is what a
   financial control looks like."*

## Reproducibility test

```bash
cd backend && .venv/bin/python tests/test_reproducibility.py
```

Prints the run summary and `REPRODUCIBILITY: PASS` with the SHA-256 hash (also
verified inside the container — identical hash across host and Docker).

## Tests

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
cd backend && .venv/bin/python -m pytest tests/ -q     # 124 passed
```

Suites: config schema v2 (validation + deterministic repair), engine (waterfall
scenario table + reproducibility), seed integrity, auth/roles, governance
(maker≠checker at API and DB, write-off ceilings, expiry), regulatory
(EMIR/CASS), agents (classifier, routing bands, Loop A caps), and a 20-step
end-to-end API workflow including the client portal.

```bash
npm --prefix frontend run build                        # type-check + build
```

## Architecture decisions

- **Why the LLM never matches at runtime** — matching must be auditable,
  reproducible, and cheap. A versioned rule is explainable; one inference per
  transaction is none of those things. The LLM's output is always forced
  through JSON-schema validation with *deterministic* repair — never "ask the
  model to fix it".
- **Why SHA-256 over canonical output** — amounts are formatted `"{:.2f}"` and
  quantities `"{:.6f}"` before hashing, and match records are sorted, so
  float noise and iteration order can never change the hash. Reproducibility
  becomes a one-click control.
- **Why maker-checker everywhere** — configs, break resolutions, Loop A
  re-versions, and EMIR filings all pass the same gate; `maker != checker` is a
  database CheckConstraint, not just UI. Journal entries are export-only;
  audit log and match ledger are append-only.
- **Why the autonomy dial** — the Judge's bands are enforced in code (an LLM may
  recommend; code decides): below 0.65 the SME *refuses to classify* and a
  senior reviews; 0.90+ resolves straight-through into resolution memory; a
  regulatory flag overrides everything.

## Regulatory features

- **EMIR Article 15** — every run screens breaks (EUR-converted via fx_rates);
  qualifying disputes flag the break, draft a notification for the competent
  authority, and wait for a CHECKER/DSI to file. Nothing is auto-filed.
- **CASS 7A** — daily client-liability vs safeguarded-funds reconciliation per
  account; shortfalls above €1,000 escalate, and every day yields a
  deterministic, hash-stamped resolution pack.
- **Evidence packs** — client-facing recon results carry a `document_hash` over
  the reconciliation facts, so a pack can be re-requested and verified byte-for-byte.

## Competitive position

AutoRek, Duco, and SmartStream automate matching. ReconOS additionally makes the
matching *provably deterministic* (one-click hash reproduction), explains every
break with a three-layer root-cause tree instead of a code, learns new
tolerances only through a human-approved what-if loop, files nothing to a
regulator without a named approver, and hands clients a self-service portal with
tamper-evident results — while the LLM stays where it belongs: authoring rules
and prose, never touching a transaction.

## Project structure

```
backend/
  app/
    engine/            # deterministic core: transforms, business days, position
                       # proof, subset-sum, 7-pass waterfall, classifier, hashing
    llm/               # pluggable providers (stub default, gemini, openai-compat)
    routers/           # auth, configs, runs, breaks, governance, regulatory,
                       # loops, client portal, audit, seed
    agents.py          # SME analysis, Judge routing bands, Loop A proposals
    services_run.py    # run orchestration: execute → persist → screen → analyze
    services_governance.py / services_regulatory.py
    seed/generator.py  # 25-row IBOR vs 21-row custody dataset + 6 aux files
  tests/               # 124 tests incl. the standalone reproducibility runner
frontend/
  src/pages/           # Dashboard, Configure, Breaks, Governance, Learning,
                       # Regulatory, ClientPortal (+ role-based sidebar)
docs/                  # RECONOS_UPGRADE_PLAN.md, HANDOVER.md
AGENTS.md              # working agreement for AI agents in this repo
```

## Configuration

Everything lives in `.env` (see `.env.example`): `DATABASE_URL` (SQLite),
`LLM_PROVIDER`/`GEMINI_API_KEY`, `SECRET_KEY`, `STP_THRESHOLD`, write-off and
EMIR/CASS thresholds, and subset-sum performance guards. Docker Compose passes
all of them through.

## Stopping

```bash
docker compose down        # keep the SQLite volume
```
```bash
docker compose down -v     # destroy it (fresh DB next start)
```
