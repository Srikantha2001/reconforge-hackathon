# HANDOVER — ReconForge (→ ReconOS upgrade)

Give this document to any model/session that will work on this repo. It contains the current
state, the conventions that must not be broken, how to run and verify everything, and the
pointer to the upgrade plan.

---

## 1. What this project is

**ReconForge** — a reconciliation platform built for a hackathon, currently fully working
end-to-end. Core idea: an LLM **authors** reconciliation configs from natural language at
design-time; a **deterministic pandas engine** does all transaction matching at run-time
(the LLM never touches transaction data); breaks are classified by a deterministic SME
classifier + advisory LLM and routed by a Judge with an STP confidence threshold; two
human-approved learning loops improve the system (Loop A: manual-match patterns → config
re-versioning through maker-checker; Loop B: resolution memory that short-circuits repeat
break patterns). Every run produces a canonical SHA-256 `output_hash`; identical input must
reproduce it bit-for-bit.

**Status: the ReconOS upgrade is COMPLETE (P1–P10, 2026-07-22).** The plan in
`docs/RECONOS_UPGRADE_PLAN.md` documents every phase with per-phase status notes and
decisions. Future work starts from this finished state — read AGENTS.md first, keep the
laws intact and the suites green.

## 2. Stack & locked decisions (do not re-litigate; ask the user if blocked)

- **Backend:** Python 3.11 (Docker) / 3.9 host-compatible, FastAPI, **sync** SQLAlchemy,
  pandas, Pydantic v2, `jsonschema` (Draft-7) for the config contract.
- **DB:** **SQLite only** (`sqlite+pysqlite:///./data/reconforge.db`). Postgres was fully
  removed on 2026-07-22 by user decision (reversing the earlier "I1"): no psycopg2, no
  Postgres compose service — do not reintroduce. Docker compose runs the backend with the
  SQLite file in the `backend_data` named volume.
- **Frontend:** React 18 + TypeScript + Vite + **MUI v9** (not Tailwind). Design system:
  warm off-white canvas `#F7F4EE`, white cards, hairline borders, single accent
  bottle-green `#1F4B3F`, Schibsted Grotesk for UI text, Spline Sans Mono for every numeral
  (via the `Figure` component). Theme in `frontend/src/theme.ts`.
- **LLM:** pluggable provider layer (user decision "B1"): `stub` (deterministic, offline,
  default), `gemini`, `openai_compat` — all selected by env `LLM_PROVIDER`; real providers
  always degrade to the stub on error. All config in `.env` / `.env.example` (single place).
- **Config-schema philosophy** (user decision "D1"): schema and deterministic engine
  co-evolve — breaking the config contract is allowed when the engine changes with it.
- **Maker-checker:** `maker != checker` enforced at the API AND by a DB CheckConstraint
  (P2/P5); journal entries export-only; audit log + match ledger append-only.
- Commit only when the user asks. There is a git repo; `main` branch.

## 3. Repo map (current, working state)

```
backend/
  app/
    config.py          # pydantic-settings Settings + cached get_settings()
    config_schema.py   # P2 DONE: config JSON Schema V2 + validate/repair-on-fail (deterministic)
    db.py              # engine/session; init_db() creates tables (no Alembic)
    models.py          # P2 DONE: 13 tables — 6 extended (ReconConfig[semver/recon_type/
                       # SUPERSEDED], Run, Break[archetype/causal_origin/root_cause_tree/
                       # regulatory/autonomy], ManualMatch, ResolutionMemory[usage_count],
                       # AuditLog[append-only]) + 7 new (User, MatchLedger[append-only],
                       # GovernanceAction[DB maker!=checker], JournalEntry[export-only],
                       # RegulatoryNotification, CassReconciliation, LoopASuggestion);
                       # all money/qty Numeric(20,6)
    auth.py            # P4 DONE: bcrypt + PyJWT, get_current_user, require_role,
                       # 5 demo users (maker/checker/admin/client/dsi) + seeding
                       # (P8 deleted app/actors.py — JWT replaced the acting-as roster)
    schemas.py         # Pydantic I/O models
    services.py        # P8: trimmed to shared helpers (audit + CSV/file I/O);
                       # v1 orchestration moved to services_run/governance/regulatory
    services_governance.py  # P5 DONE: maker_submit / checker_approve (maker!=checker
                       # at API + DB), export-only journal entries, expiry sweep,
                       # small-write-off STP auto-approve, FORCE_MATCH -> ManualMatch
    services_regulatory.py  # P6 DONE: screen_breaks_for_emir (EUR>15M & age>15d ->
                       # DRAFT notification), approve DRAFT->FILED, cass_daily
                       # (ACC002 5k shortfall), cass_resolution_pack (stable hash)
    agents.py          # P7 DONE: sme_analyze / judge_route (code-enforced bands) /
                       # detect_loop_a_pattern + propose_loop_a_change (cap 5d)
    services_run.py    # P8 DONE: execute_run (persist Run+Breaks+MatchLedger, position
                       # proof, EMIR screen), reproduce, analyze_run_breaks (SME+Judge,
                       # STP auto-resolve), Loop A detect/propose/what-if
    engine/            # P3 DONE: v2 deterministic engine (pandas-only, no LLM)
      transforms.py    # registry: sign_flip/abs_value/upper_case/lower_case/strip/
                       # round2/strip_leading_zeros/date_normalise/compute_market_value/
                       # enrich_from_aux/corporate_action_adjust (all null-safe)
      business_days.py # business-day date distance (weekends + market holidays)
      aux.py           # loads auxiliary_files into {alias: DataFrame}
      subset_sum.py    # SubsetSumMatcher (group-size/partition/timeout guards)
      position_proof.py# opening + movement == closing per side -> PROVED/PARTIAL/UNPROVED
      matching.py      # MatchingWaterfall: 5 pass types, Decimal value rules,
                       # business-day DATE_TOLERANCE, restrict_isins scoping
      archetype.py     # P7 DONE: deterministic 12-archetype classifier (+9 causal
                       # origins, root_cause_tree); pure, no LLM/DB
      hashing.py       # assign_row_ids + canonical .2f/.6f sorted match hash (Law 4)
      runner.py        # reconcile(df_a, df_b, config, aux_data, run_date, data_dir)
                       # -> ReconResult. Pipeline: transforms -> drop-zero-qty ->
                       # pre-match dedup -> position proof -> waterfall ->
                       # residual/explained breaks -> hash
    llm/               # base.py ABC; stub.py (deterministic); gemini.py; openai_compat.py
    seed/generator.py  # P1 DONE: ReconOS securities dataset — 25-row internal_ibor.csv,
                       # engineered bny_mt535_custody.csv (7 pass fixtures + all breaks),
                       # 6 aux files, v2 default_config.json; all literals, byte-identical;
                       # SCENARIOS table is the source of truth for tests; CLI --out
    routers/           # auth (P4), governance (P5), regulatory (P6), client (P8),
                       # configs/runs/breaks/loops (v2, P8), audit, seed
    main.py            # FastAPI app, lifespan init_db + seed_demo_users, CORS, /api prefix
  tests/               # conftest (env vars at MODULE level — see gotchas)
                       # 124 passing / 0 known-red (v2 e2e as of P8)
  data/                # generated seed: internal_ibor.csv, bny_mt535_custody.csv,
                       # 6 aux files, default_config.json (v2)
  Dockerfile           # py3.11-slim, generates seed at build, uvicorn :8000
  .venv/                # host-side venv (python3.9); .venv/bin/python -m pytest tests/ -q
frontend/
  src/
    App.tsx            # P9: role-based page router (Dashboard/Configure/Breaks/
                       # Governance/Learning/Regulatory/Client) + login gate
    api.ts             # P9: v2 API client (Bearer, 401->logout), /api -> :8000
    types.ts           # P9: v2 types (hand-synced with schemas.py)
    theme.ts           # design system (bottle-green) + v2 statusColor map
    context/AuthContext.tsx  # P4/P9: JWT (token in localStorage), useAuth
    components/        # P9: PositionProofCard, WaterfallChart, RootCauseTree,
                       # StatusChip, Sidebar(role nav) + Figure/SeverityChip/
                       # ConfidenceBadge/VersionChip/SplitMatchedBar
    pages/             # P9: Login, Dashboard, Configure, Breaks, Governance,
                       # Learning, Regulatory, ClientPortal
    utils/csv.ts       # client-side CSV header sniff (first 4KB, naive comma split)
    context/ActorContext.tsx   # "acting as" (localStorage) — becomes AuthContext in upgrade
    components/        # Sidebar, BreakDrilldown (inspect/advise/manual-match/resolve dialog),
                       # Figure, VersionChip, SplitMatchedBar, DoubleRuleTotal, SeverityChip,
                       # ConfidenceBadge, RuleTable, EditableRuleTable
    pages/             # ConfigureStep (upload-first -> NL describe -> review/approve),
                       # RunStep (run + result + breaks board inline), LoopAStep, AuditStep
docker-compose.yml     # db (postgres:16-alpine, healthcheck) + backend (build ./backend)
.claude/launch.json    # "frontend-dev": npm --prefix frontend run dev -- --host, port 5173
.env / .env.example    # ALL config: POSTGRES_*, DATABASE_URL, LLM_*, STP_THRESHOLD, UPLOAD_DIR, FRONTEND_ORIGIN
AGENTS.md              # quick-start agent guidance (laws, commands, phase status) — read first
docs/RECONOS_UPGRADE_PLAN.md   # THE PLAN — phased tasks P1..P10 with acceptance criteria
```

## 4. How to run & verify

```bash
# 1. Backend (SQLite; http://localhost:8000/api/health -> {"status":"ok","llm_provider":"stub"})
docker compose up -d --build

# 2. Frontend dev server (proxies /api -> :8000)
npm --prefix frontend run dev

# 3. Backend tests (venv at backend/.venv; host python3 is 3.9 and has no deps globally)
cd backend && .venv/bin/python -m pytest tests/ -q
#   -> 124 passing / 0 known-red as of P8. The v1 test_api set was replaced
#      by the v2 e2e suite. All green: config_schema, engine, reproducibility,
#      seed, auth, governance, regulatory, agents, api.

# Demo login (5 users): maker@db.com/maker123, checker@db.com/checker123,
# admin@db.com/admin123, client@alphacapital.com/client123, dsi@db.com/dsi123

# Standalone reproducibility proof (prints PASS + SHA-256):
cd backend && .venv/bin/python tests/test_reproducibility.py

# 4. Frontend type-check + build
npm --prefix frontend run build

# 5. Regenerate seed data (deterministic literals — byte-identical on re-run)
cd backend && .venv/bin/python -m app.seed.generator --out ./data
```

UI walkthrough (current): login-less. Sidebar → **Configure** (toggle seeded pair or upload
2 CSVs → describe in English → Author config → review rules → switch "Acting as" to a
different actor → Approve) → **Run & breaks** (Run reconciliation → match-rate/hash/result +
breaks board on the same screen → Inspect a break → Advise / Manual match / Resolve) →
**Learning loops** (aggregate manual matches → propose → what-if → approve & re-run) →
**Audit log**. Demo showstopper: manually match the 5 DRF drift breaks → Loop A proposes
tolerance 2→3 days → approve as checker → match rate 74.7% → 81.3%.

## 5. Invariants that must survive any change

1. LLM authors configs / advises on breaks only — **never** matches transactions.
2. Engine is deterministic; `output_hash` reproducible (there is a reproducibility endpoint
   and test — keep them green).
3. Config changes only go live through maker-checker approval (`approver != author`), incl.
   Loop A re-versions. Nothing changes silently; what-if previews never hide newly-broken keys.
4. Schema validation failures are repaired **deterministically** (`repair()` in
   config_schema.py), never by asking the LLM to fix JSON.
5. Every mutating action writes an `AuditLog` row (actor, action, before/after, confidence).
6. Stub provider must stay fully deterministic — reproducibility tests depend on it.

## 6. Gotchas (each cost real debugging time — don't rediscover them)

- **pydantic-settings caching:** `get_settings()` is `lru_cache`d and `app.db` reads it at
  import time. Tests set env vars at **module level** in `conftest.py` (not in fixtures) —
  keep it that way or the DB URL override silently misses.
- **FastAPI lifespan in tests:** use `with TestClient(app) as c:` — without the context
  manager, startup (table creation) never runs → "no such table".
- **MUI v9:** `Stack`/`Typography` no longer accept `alignItems`/`justifyContent`/
  `flexWrap`/`fontFamily` as direct props — put them in `sx={{…}}`. `TextField` uses
  `slotProps={{ htmlInput: {…} }}` instead of `inputProps`.
- **Backend venv:** host `python3` is 3.9 with no packages — use `backend/.venv`
  (`.venv/bin/python -m pytest …`). Keep backend code Python-3.9-compatible (Docker is 3.11).
- **Vite dev server:** started via `.claude/launch.json` (`--prefix frontend` is required —
  repo root has no package.json). Browser-verify with the preview tools; prefer
  `read_page` refs over raw coordinates for clicks (re-renders shift positions).
- **Seed rows use fixed amounts** (not random) for tolerance-sensitive archetypes so the
  ratio heuristics don't misclassify — preserve that property in any new seed data.
- Engine classifier ordering matters: fx-rounding (≤0.05) must be checked **before**
  fee-diff (≤5) or the branch is dead.

## 7. Where the new requirement comes from

The ReconOS spec is a 10-prompt build document (PDF at `~/Downloads/claudeprompt.pdf`;
text-extracted copy may exist in the session scratchpad). **Do not follow its prompts
literally** — it assumes greenfield (SQLite, async, Tailwind, `reconos/` tree). The
authoritative reconciliation of that spec with this codebase is
`docs/RECONOS_UPGRADE_PLAN.md`: stack decisions (§1), adopted laws (§2), gap analysis (§3),
phased tasks P1–P10 with files-to-touch and acceptance criteria (§4), sequencing (§5).

**Execution contract for a new session:**
1. Read this file, then `docs/RECONOS_UPGRADE_PLAN.md` in full.
2. Pick the next unfinished phase (P1→P10 in order). Verify current state first
   (`pytest -q`, `npm run build`, `docker compose up -d`).
3. Hard gate: P3's reproducibility test must pass before any P9 frontend work.
4. After each phase: run its acceptance criteria, keep all suites green, browser-verify UI
   phases, and update the phase status inside the plan doc (mark `✅ DONE` + date + notes).
5. No git commits unless the user asks.
