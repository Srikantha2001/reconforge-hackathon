# AGENTS.md — ReconForge / ReconOS

Guidance for any AI agent working in this repo. Read this first, then
`docs/HANDOVER.md` (full context) and `docs/RECONOS_UPGRADE_PLAN.md` (the
active work plan) before writing code.

## What this is

A reconciliation platform: an LLM authors recon configs from natural language
at design-time; a deterministic pandas engine does ALL transaction matching at
run-time; breaks are classified and routed with human maker-checker
governance; two approved learning loops (A: config refinement, B: resolution
memory) improve it. Currently mid-upgrade from **ReconForge** (v1, working)
to **ReconOS** (v2 spec) via phases P1–P10 in `docs/RECONOS_UPGRADE_PLAN.md`.

## Current phase status

- **P1 DONE (2026-07-22):** securities seed dataset v2 lives in
  `backend/app/seed/generator.py` → `backend/data/` (internal_ibor.csv,
  bny_mt535_custody.csv, 6 aux files, v2 default_config.json). Old
  ledger/statement pair removed.
- **P2 DONE (2026-07-22):** config schema v2 (`config_schema.py`), 13-table
  data model (`models.py` — 6 extended + 7 new, `Numeric(20,6)` money, DB-level
  `maker != checker` CheckConstraint, append-only match_ledger/audit_log), v2
  Pydantic I/O (`schemas.py`), new Settings (`config.py` — auth/governance/
  regulatory/subset-sum keys) mirrored in `.env`/`.env.example`. App boots and
  creates all 13 tables on fresh SQLite. `test_config_schema.py` rewritten for
  v2 (22 tests).
- **P3 DONE (2026-07-22):** engine v2 in `backend/app/engine/` — `transforms.py`
  (registry, 11 ops, null-safe), `business_days.py`, `aux.py`, `subset_sum.py`
  (guarded), `position_proof.py`, `matching.py` (`MatchingWaterfall`, 5 pass
  types, Decimal value rules, `restrict_isins` scoping), `hashing.py` (canonical
  `.2f`/`.6f` match hash), `runner.py` (`reconcile()` orchestrates transforms →
  drop-zero-qty → pre-match dedup → position proof → waterfall → residual/
  explained breaks → hash). Seed resolves exactly: 14 matched (passes 5-2-1-1-1
  -2-2), 9 open breaks (2 duplicate, 4 drift, TRD021 misbooking, TRD022 EMIR,
  TRD019 missing leg), TRD024 = CORPORATE_ACTION explained. Reproducible hash
  verified host + container (identical). `test_engine.py` rewritten + new
  `test_reproducibility.py` (standalone: `python tests/test_reproducibility.py`).
- **P4 DONE (2026-07-22):** JWT auth + 5 roles. `backend/app/auth.py` (bcrypt
  hashing, PyJWT HS256, `get_current_user`, `require_role(*roles)`, 5 demo users
  + idempotent `seed_demo_users`), `routers/auth.py` (`POST /api/auth/login`,
  `GET /api/auth/me`, `GET /api/auth/probe-maker` role-gate demo). `main.py`
  seeds users at startup, includes auth router, drops the actors router. Deleted
  `routers/actors.py`; **`app/actors.py` kept** (v1 routers still import
  `is_valid_actor` until P8 rewires them). Frontend: `context/AuthContext.tsx`
  (token in localStorage, `useAuth`, plus a `useActor` compat shim so v1 pages
  compile), `pages/LoginPage.tsx`, `api.ts` Bearer header + 401→logout, `App.tsx`
  login gate, `Sidebar.tsx` user/role/logout. `test_auth.py` (14 tests). Verified
  live: login all roles, wrong pw 401, require_role 403, logout cycle.
- **P4/P8 boundary (now resolved):** P4 built auth infrastructure + login; P8
  rebuilt the config/run/break/loop endpoints for v2 with per-endpoint role gates
  and actor-from-token. `app/actors.py` and the `actor_id` request-body fields are
  gone as of P8.
- **P5 DONE (2026-07-22):** governance service. `services_governance.py`
  (`maker_submit` → PENDING + break PENDING_CHECKER_APPROVAL + 24h expiry;
  `checker_approve` → maker≠checker 400 + DB constraint backstop, expiry check,
  WRITE_OFF >10k blocked, approve → RESOLVED_APPROVED + export-only JournalEntry
  [sha256 audit_reference] + resolution memory; FORCE_MATCH also writes a
  ManualMatch for Loop A; reject/expire → break back to open; small write-offs
  <500 auto-approve via `STP_AUTO` sentinel), `routers/governance.py`
  (maker-submit [MAKER], checker-approve [CHECKER], pending [CHECKER, w/ expiry
  sweep + time_remaining], audit [any, paginated]). First real use of P4's
  `require_role`. `test_governance.py` (10 tests). Verified live in container:
  full submit→approve→journal e2e + role-gating (401/403/404/200).
- **P6 DONE (2026-07-22):** regulatory services. `services_regulatory.py`
  (`screen_breaks_for_emir` — EUR-converts break amount via fx_rates; if > 15M
  AND age > 15 business days → break.regulatory_escalation_required + DRAFT
  RegulatoryNotification w/ deterministic narrative; `approve_emir_notification`
  DRAFT→FILED + audit; `cass_daily` — per-account liability vs safeguarded from
  cass_safeguarded.csv, aggregate shortfall, SHORTFALL_DETECTED if > 1000, hashed
  resolution pack, idempotent per date; `cass_resolution_pack` — stable-hash
  JSON), `routers/regulatory.py` (EMIR list/approve [CHECKER|DSI], CASS daily +
  resolution-pack [CHECKER|DSI], CSDR → `[]` minimal). `test_regulatory.py`
  (8 tests). Verified live: ACC002 5,000 EUR shortfall detected, EMIR role-gated,
  hashes stable. EMIR narrative is deterministic (offline-stub posture); a real
  LLM narrative can be plugged in later.
- **P7 DONE (2026-07-22):** agent layer v2. `engine/archetype.py` rewritten —
  deterministic 12-archetype classifier (+ 9 causal origins, field_most_responsible,
  confidence, 3-layer root_cause_tree {data_layer, rule_that_failed, ai_diagnosis});
  pure, no LLM/DB. New `app/agents.py`: `sme_analyze` (classifier + resolution
  prose + Loop B few-shot recall + refuse_to_classify <0.65), `judge_route`
  (code-enforced bands: regulatory flag → REGULATORY_ESCALATION wins; <0.65 →
  ESCALATE_SENIOR; ≥stp_threshold → STP_AUTO_RESOLVE; else MAKER_REVIEW_REQUIRED),
  `detect_loop_a_pattern` + `propose_loop_a_change` (date-drift/qty-rounding
  detectors, DATE_TOLERANCE capped at 5, semver minor-bump, deepcopy isolation).
  `retrieve_similar_cases` bumps usage_count/last_used_at. `test_agents.py`
  (18 tests, drives real seed breaks). These are pure functions; P8 wires them
  into the run/analyze/loop-a endpoints. No new routes in P7.
- **P8 DONE (2026-07-22):** API completion + client portal — the phase that
  rewired everything to v2 and cleared the known-red tests. New
  `services_run.py` (execute_run persists Run + Breaks[open/explained] +
  MatchLedger, position proof, P6 EMIR screen; reproduce; analyze_run_breaks =
  P7 SME+Judge over open breaks, STP auto-resolve; Loop A detect/propose/what-if).
  Rewrote all four routers for v2 + JWT roles: `configs` (author→submit→approve/
  reject, versions, SUPERSEDED on re-version), `runs` (execute[MAKER], reproduce,
  position-proof, waterfall, summary), `breaks` (analyze[MAKER], filters,
  regulatory[CHECKER|DSI]), `loops` (Loop A aggregate/propose/what-if, Loop B
  memory). New `routers/client.py` (CLIENT: upload→run vs bank IBOR by fund,
  simplified recon, evidence pack w/ stable document_hash, run isolation via
  Run.client_id). Added Run.client_id/is_client_run. `services.py` trimmed to
  shared helpers (audit + CSV/file I/O). Deleted `app/actors.py` (finally).
  `test_api.py` rewritten: 20-step v2 e2e. Stub `summarize_config` made v2-aware.
- **ALL BACKEND SUITES GREEN: 124 passing / 0 known-red.** The v1 known-red set
  is gone. Verified live in-container (full author→approve→run→analyze flow +
  client portal + evidence-hash stability + isolation).
- **⚠ Frontend is now stale against the v2 backend** — its api.ts still calls the
  removed v1 endpoints (actor_id in body, /reproducibility-check, etc.). It still
  *builds* (TS compiles), but the running app won't work until **P9** rebuilds it.
- **P9 DONE (2026-07-22):** frontend v2 — full rebuild against the v2 API, keeping
  the bottle-green design system + `Figure` numerals. Rewrote `types.ts` + `api.ts`
  (all v2 endpoints, Bearer, 401→logout), cleaned `AuthContext` (dropped the
  `useActor` shim). Role-based `Sidebar` (MAKER/CHECKER/ADMIN internal nav; CLIENT
  → portal only; DSI → Regulatory) + `App.tsx` page router with per-role default
  landing. New components: `PositionProofCard` (traffic light + Opening/+Movement/
  =Closing + truncated hash + Reproduce PASS/FAIL), `WaterfallChart` (hand-rolled
  stacked bars, no new deps), `RootCauseTree` (3-layer Data/Rule/AI boxes),
  `StatusChip`. New pages: Dashboard (run control, KPIs, proof, waterfall, top
  breaks), Configure (author→submit→approve, versions, JSON viewer), Breaks
  (filters, analyze, drilldown w/ tree + regulatory narrative + governance
  actions), Governance (checker queue w/ countdown, audit log), Learning (Loop A
  propose/what-if/approve, Loop B memory), Regulatory (EMIR/CASS/CSDR tabs),
  ClientPortal (upload→match-rate→evidence download). Deleted all v1 pages/
  components. `npm run build` clean. **Browser-verified live:** login (all roles),
  MAKER dashboard (PROVED, Reproduce PASS, 7 passes), breaks analyze + root-cause
  tree + EMIR narrative, role-gated nav, CLIENT portal-only.
- **P10 DONE (2026-07-22) — ALL PHASES COMPLETE.** docker-compose now passes
  through every P2+ setting (SECRET_KEY, write-off/EMIR/CASS thresholds,
  subset-sum guards); Dockerfile seed generation fails loudly (no `|| true`);
  README fully rewritten for ReconOS (quick start, demo users, 8-step demo
  script ending on the Reproduce moment, architecture decisions, regulatory
  features, competitive position). Verified: container rebuild healthy, env
  passthrough confirmed in-container, in-container reproducibility PASS
  (hash `5cc8ff8d…`), 124 tests green, frontend build clean, live login/docs 200.
  **Not done (stretch, needs user ask):** DB yellow/navy re-skin — the app keeps
  the bottle-green design system.
- **The ReconOS upgrade is finished.** Future work starts from this state; keep
  the laws, the suites green, and the docs in sync.
- **Resolved P3 design decisions (user-approved 2026-07-22):** (1) pass 6/7
  separation via optional `restrict_isins` per pass (passes 5/6/7 each scoped to
  their fixture ISIN); (2) duplicates → pre-match dedup, surplus flagged
  `duplicate_entry` both sides; (3) TRD024 → position-control explained break
  (`explained_break_categories`), not a transform-match. Also added: passes 1/2
  check `computed_market_value` EXACT and pass 3 a rounding-scale (5.0) mv guard,
  so price disputes (TRD013→pass 4, TRD022→break) aren't silently swallowed.
- **No known-red as of P8.** The v1 `test_api` set was replaced by the v2 e2e
  suite. **All backend suites green: 124 passing / 0 failing** (config_schema,
  engine, reproducibility, seed, auth, governance, regulatory, agents, api).

## Laws (never violate)

1. Matching engine = pure Python/pandas. Zero LLM at run-time.
2. Monetary amounts as NUMERIC/Decimal, never float (enforced from P2 on).
3. Amounts `f"{v:.2f}"`, quantities `f"{v:.6f}"` before comparison/hashing.
4. SHA-256 output hash: same input → same hash, always. Keep reproducibility
   tests green.
5. maker_id ≠ checker_id (DB constraint from P2 on; service check today).
6. Audit log and match ledger are append-only.
7. LLM unavailable → deterministic stub fallback / route to human. Never crash.
8. Journal entries are export-only, never auto-posted.
9. Config JSON repairs are deterministic (`config_schema.repair`) — never ask
   an LLM to fix JSON.
10. Every file complete and runnable — no stubs, no TODOs.

## Stack (locked — ask the user before deviating)

- Backend: FastAPI + **sync** SQLAlchemy + pandas + Pydantic v2 + jsonschema.
- DB: **SQLite only** (`DATABASE_URL=sqlite+pysqlite:///./data/reconforge.db`).
  Postgres was fully removed 2026-07-22 by user decision — do not reintroduce.
- Frontend: React 18 + TS + Vite + **MUI v9** with the bottle-green design
  system in `frontend/src/theme.ts` (NOT Tailwind). Numerals use the `Figure`
  component (Spline Sans Mono).
- LLM: pluggable via `LLM_PROVIDER` env — `stub` (deterministic, default),
  `gemini`, `openai_compat`. All adapters degrade to the stub on error.
- All configuration lives in `.env` / `.env.example` — nothing reads
  `os.environ` outside `backend/app/config.py`.

## Commands

```bash
# Backend deps (venv at backend/.venv, host Python 3.9-compatible)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Backend tests
cd backend && .venv/bin/python -m pytest tests/ -q

# Regenerate seed data (deterministic, byte-identical)
cd backend && .venv/bin/python -m app.seed.generator --out ./data

# Backend via Docker (SQLite inside the container, named volume backend_data)
docker compose up -d --build      # health: curl localhost:8000/api/health

# Frontend dev server (proxies /api -> :8000); use the Browser-pane preview
# tools with .claude/launch.json entry "frontend-dev" — never Bash for servers
npm --prefix frontend run dev
npm --prefix frontend run build   # type-check + build gate
```

## Workflow rules

- Execute plan phases **in order**; get explicit user approval before starting
  each next phase. Never batch ahead.
- Hard gate: P3's reproducibility test must pass before any P9 frontend work.
- After each phase: run that phase's acceptance criteria from the plan, keep
  all non-known-red suites green, browser-verify UI changes, and update the
  phase status in `docs/RECONOS_UPGRADE_PLAN.md` and in this file.
- When the spec is ambiguous, ask the user — do not assume silently. Record
  resolved decisions in the plan doc.
- No git commits/pushes unless the user explicitly asks.
- Temporary files go to the session scratchpad, never into the repo.

## Gotchas (cost real debugging time)

- `get_settings()` is `lru_cache`d and read at import time by `app.db` —
  tests must set env vars at **module level** in `tests/conftest.py`.
- Use `with TestClient(app) as c:` or FastAPI lifespan (table creation)
  never runs.
- MUI v9: layout props (`alignItems`, `flexWrap`, `fontFamily`…) belong in
  `sx={{…}}`; `TextField` uses `slotProps={{ htmlInput: … }}`.
- Seed data is all literal strings — regeneration must stay byte-identical;
  never introduce RNG or float reformatting (files are written verbatim,
  DataFrames are parsed FROM the literals).
- Browser verification: prefer `read_page` ref-based clicks over raw
  coordinates (re-renders shift positions).
- Host Python is 3.9 (Docker image is 3.11) — keep backend code 3.9-compatible.
