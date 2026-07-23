# ReconOS Upgrade Plan — evolving ReconForge into ReconOS

**Status:** PLANNED (no code written yet)
**Source requirement:** `~/Downloads/claudeprompt.pdf` — "ReconOS: AI-native reconciliation
platform for Deutsche Bank Securities Services" (10-prompt build spec).
Extracted text archived for reference at the end of `docs/HANDOVER.md`'s pointer section.

**Prime directive from the user:** plug the new features into the **existing ReconForge
codebase** (`backend/app/…`, `frontend/src/…`). Do NOT scaffold the PDF's `reconos/backend/src/…`
tree from zero. Everything below is expressed as a delta against what already exists.

Read `docs/HANDOVER.md` first — it describes the current state of the codebase, its
conventions, and how to run/verify it. This plan assumes that context.

---

## 1. Stack decisions (existing project wins over PDF where they conflict)

These are deliberate overrides of the PDF spec, consistent with earlier locked user
decisions. Do not silently re-litigate them; if one blocks you, ask the user.

| Topic | PDF says | We do | Why |
|---|---|---|---|
| Database | SQLite + aiosqlite (async) | **SQLite + sync SQLAlchemy** (user reversed I1 on 2026-07-22: Postgres fully removed — no psycopg2, no db compose service) | Whole service layer is sync — async rewrite = starting over |
| Repo layout | `reconos/backend/src/…` | Keep `backend/app/…` | Plug-in, not rebuild |
| Frontend styling | Tailwind + shadcn/ui, DB yellow/navy | **Keep React + MUI + existing bottle-green theme** | Design system already built; re-skinning is optional polish at the end (see P10 stretch) |
| LLM | Hard Gemini dependency | **Keep pluggable provider layer** (`stub`→default/fallback, `gemini`, `openai_compat`) | Existing law B1; Gemini works when `LLM_PROVIDER=gemini` + key. PDF Law 8 (never crash, route to maker review) is already our stub-fallback ladder — adapt response shape only |
| Charts | Recharts | MUI + existing components; add small SVG/bar viz by hand or `recharts` if genuinely needed for the waterfall chart | Keep deps lean; recharts is acceptable if hand-rolling is slower |
| Auth | JWT (PyJWT/jose), 5 roles | **Adopt JWT** — this genuinely replaces the "acting as" selector | New requirement is explicit; client portal needs real role separation |

## 2. Laws to adopt (from the PDF — enforce during every task)

1. Matching engine is pure Python/pandas. Zero LLM at run-time. *(already law)*
2. Monetary amounts stored as `NUMERIC`/`Decimal`, never float. *(NEW — migration needed)*
3. Amounts formatted `f"{val:.2f}"` (quantities `f"{val:.6f}"`) before any comparison or hashing. *(NEW)*
4. SHA-256 output hash deterministic: same input → same hash. *(already law; canonical spec extended)*
5. `maker_id != checker_id` enforced at **database constraint level**, not just service code. *(NEW — currently service-level only)*
6. Audit log append-only — no UPDATE/DELETE ever. *(service-layer enforcement + no update paths)*
7. Match ledger append-only. *(NEW table, same rule)*
8. LLM unavailable → `{"status":"LLM_UNAVAILABLE","fallback":"ROUTE_ALL_TO_MAKER_REVIEW"}` — never crash. *(map onto existing stub fallback)*
9. Journal entries are never auto-posted. Export only. *(NEW)*
10. Every file complete and runnable — no stubs, no TODOs. *(standing practice)*

## 3. Gap analysis (existing → target)

| Capability | ReconForge today | ReconOS target | Verdict |
|---|---|---|---|
| Engine | single-pass exact-key join + rule eval | 7-pass matching waterfall (exact → date-tol → qty-round → fx-round → 1:N → N:1 → N:M subset-sum) | **extend** `engine/` |
| Position control | none | opening + movement = closing proof per side, explained categories | **new** module |
| Transforms | abs/upper/lower/strip/round2 | + sign_flip, strip_leading_zeros, date_normalise(fmt), compute_market_value, enrich_from_aux, corporate_action_adjust | **extend** |
| Aux data | none | fx_rates, instrument_master, account_aliases, market_holidays, corporate_actions, cass_safeguarded | **new** seed files + loader |
| Config schema | frozen v1 (sources, transforms, match_rules) | v2: + recon_type, source_topology, aux_files, position_control, matching_waterfall passes, regulatory_config, autonomy_config, output_hash_spec, semver versions, SUPERSEDED status | **extend** `config_schema.py` (breaking change, D1 allows co-evolving engine) |
| Actors/auth | seeded "acting as" selector, no login | JWT login, 5 roles (ADMIN/MAKER/CHECKER/CLIENT/DSI), demo users | **replace** |
| Maker-checker | config approval only, service-level check | + GovernanceAction lifecycle on breaks (FORCE_MATCH/WRITE_OFF/INVESTIGATE/AWAIT_COUNTERPARTY), expiry, write-off €-thresholds, DB CheckConstraint | **extend** |
| Journal entries | none | generated on approval, export-only | **new** |
| Regulatory | none | EMIR Art. 15 detection + notification drafts; CASS 7A daily recon + shortfall + resolution pack; CSDR (UI stub tab acceptable) | **new** |
| SME/Judge | 10 archetypes, confidence, STP threshold | 12 archetypes, 9 causal origins, 3-layer root-cause tree, refuse_to_classify <0.65, routing bands (<0.65 ESCALATE_SENIOR / 0.65–0.89 MAKER_REVIEW / ≥0.90 STP), regulatory override | **extend** |
| Loop A | delta aggregation ≥1 group, tolerance widening | pattern types (date drift / qty rounding / ref truncation), 4+ occurrences threshold, what-if on history, cap DATE_TOLERANCE ≤ 5 days, semver bump + SUPERSEDED | **extend** |
| Loop B | feature_key memory, short-circuit | + usage_count, last_used_at, retrieval as few-shot into SME prompt | **extend** |
| Client portal | none | CLIENT-scoped upload → run vs bank records → simplified results → evidence pack w/ document hash | **new** |
| Frontend | 4 sidebar pages (Configure, Run & breaks, Learning, Audit) | + Login, Dashboard (position proof, waterfall chart, KPIs), Governance (maker/checker queues), Regulatory (3 tabs), Client portal; breaks modal gains root-cause tree | **extend** |
| Match ledger | matches only counted, not persisted | append-only `match_ledger` rows per pass | **new** table |

---

## 4. Task list (phased — execute in order; each task states files + acceptance criteria)

> Conventions for the implementing session: `docker compose up -d --build` runs the backend
> (SQLite inside the container), `preview_start frontend-dev` (`.claude/launch.json`) for the UI,
> `cd backend && .venv/bin/python -m pytest tests/ -q` for tests (venv at `backend/.venv`).
> After every phase: backend tests green (minus the documented known-red set until P2+P3) +
> `npm run build` clean.
> DB migration policy: hackathon-grade — extend `init_db`/models and recreate the schema
> (delete `backend/data/reconforge.db` / `docker compose down -v`) rather than Alembic,
> unless the user asks otherwise.

### P1 — Securities seed dataset v2 + aux files — ✅ DONE 2026-07-22
> **Status notes:** implemented strictly (user chose "strict P1 files only"): generator +
> dataset + aux files + v2 config + rewritten `test_seed.py` (8 tests green, byte-identical
> determinism verified, legacy ledger/statement removed). The v1 author-from-seed flow is
> intentionally dead until P2+P3: the 16 `test_api.py::TestFullWorkflow` tests are the
> accepted known-red set. `/api/seed/info` reports `exists:false` (legacy filenames) until P8.
> Custody `reference` naming convention (not spec-dictated): split legs `TRD014-A/-B`,
> aggregates `TRD015-16`/`TRD017-18`, duplicate posting reuses `TRD001`. EMIR
> `competent_authority` set to "BaFin" (spec left the value open).
> **Open question for P3 (flagged, needs user decision):** the pass-6 (TRD015+16) and
> pass-7 (TRD017+18) fixtures are structurally identical (two A-rows, same ISIN, summing to
> one B-row), so a generic MANY_TO_ONE pass would claim both and the subset-sum pass would
> match nothing. P3 must decide how to scope pass 6 vs pass 7 (e.g. pass ordering, group-size
> or currency scoping) — ask the user when starting P3.
**Goal:** replace the toy ledger/statement pair with the exact 25-row securities dataset from the spec.
**Files:** rewrite `backend/app/seed/generator.py` (keep module path + CLI `--out`); output to `backend/data/`:
- `internal_ibor.csv` — 25 exact rows from spec (TRD001–TRD025; TRD020 is a literal duplicate of TRD001's values; TRD023/TRD025 zero-quantity; TRD024 pre-split 5000 @ 2024-01-10).
- `bny_mt535_custody.csv` — constructed to hit every pass/break: TRD001–005 exact; TRD006–007 +2d drift (Pass 2); TRD008–011 +3d drift (4 breaks → Loop A signal); TRD012 qty 49999 (Pass 3); TRD013 price 245.68 (Pass 4); TRD014 split into 2×15000 (Pass 5); one 16000 row for TRD015+016 (Pass 6); one 10000 row for TRD017+018 (Pass 7); no row for TRD019 (missing leg); duplicate of TRD001-row (dup flag); TRD021 booked to ACC002 (misbooking); TRD022 amount 16,200,000 vs 16,500,000 (EMIR dispute >15M); TRD024 qty 10000 (2:1 corporate action explains it); nothing for TRD023/025.
- Aux CSVs exactly per spec: `fx_rates.csv`, `instrument_master.csv`, `account_aliases.csv`, `market_holidays.csv`, `corporate_actions.csv`, `cass_safeguarded.csv`.
- `default_config.json` — the v2 config (see P2) with `recon_id: recon_001`, `recon_name: DB_PositionRecon_IBOR_vs_BNYMellon_Daily`, version `1.0.0`, status APPROVED.
**Acceptance:** generator is deterministic (fixed literal rows, no RNG); a self-check function asserts each pass/break scenario is present; old seed files removed; `backend/tests/test_seed.py` rewritten to assert the scenario table above.

### P2 — Config schema v2 + data model expansion — ✅ DONE 2026-07-22
> **Status notes:** `config_schema.py` rewritten to the v2 contract (recon
> typing, semver, source topology, aux files, per-side transforms, position
> control, 7-pass waterfall, regulatory/autonomy blocks, output-hash spec) with
> deterministic repair-on-fail extended (camelCase, semver coercion, match-type
> synonyms, tolerance-on-date-rule, default governance blocks). `models.py` now
> has 13 tables: the 6 originals extended (Numeric(20,6) money/qty, break gains
> archetype/causal_origin/root_cause_tree/regulatory/autonomy fields, config
> gains recon_type/semver-version/SUPERSEDED lifecycle/superseded_by,
> resolution_memory gains usage_count/last_used_at/causal_origin) plus 7 new
> (users, match_ledger, governance_action, journal_entry,
> regulatory_notification, cass_reconciliation, loop_a_suggestion). Laws wired:
> DB `maker != checker` CheckConstraint on governance_action; append-only
> match_ledger + audit_log (no update path); journal_entry export-only.
> `schemas.py` I/O aligned to v2 (version→str, new optional break/run fields).
> `config.py`+`.env`+`.env.example` gained auth/governance/regulatory/subset-sum
> settings. `test_config_schema.py` rewritten (22 v2 tests). Verified: app boots
> + all 13 tables create on fresh SQLite (host and Docker container); 43 passing
> / 16 known-red (test_api, unchanged). **Deliberate adaptations (documented):**
> kept integer autoincrement PKs (spec's TEXT PKs would break every existing
> service/router for no gain at this scale); actor/user columns stay plain
> strings (P4 fills them; SQLite doesn't enforce FKs by default).
> **⚠ Still-open P3 question (ask user first):** pass-6 vs pass-7 fixtures are
> structurally identical — see P1 notes above.

### P2 (original spec) — Config schema v2 + data model expansion
**Goal:** extend the frozen config contract and DB models.
**Files:** `backend/app/config_schema.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/db.py` (init), `backend/app/config.py` (new settings).
- Config v2 JSON Schema: `recon_id`, `recon_name`, `recon_type` (12-value enum: POSITION, TRADE, CASH, CORPORATE_ACTION, COLLATERAL, NAV, CASS, FAILS, FX, SEC_LENDING, REPO, GL_SUBSTANTIATION), semver `version`, `status` (DRAFT/PENDING_APPROVAL/APPROVED/SUPERSEDED), `source_topology` (ONE_VS_ONE…), `sources` (side/alias/file), `auxiliary_files[]` (id, alias, file, key_column), `transforms` per side (step-ordered op list), `position_control` (enabled, per-side opening/closing/movement fields, tolerance, explained_break_categories), `matching_waterfall[]` (pass number, name, type ∈ ONE_TO_ONE / ONE_TO_MANY / MANY_TO_ONE / N_TO_M_SUBSET_SUM / CASS_SPECIFIC, key_rules, value_rules with match_type ∈ EXACT / NUMERIC_TOLERANCE / ASYMMETRIC_TOLERANCE / DATE_TOLERANCE, tolerance / tolerance_days / business_days_only / calendar_market, aggregate/group fields, performance_guard), `regulatory_config` (emir: threshold 15,000,000 EUR + 15 days; cass: CASS_7A daily, shortfall threshold), `autonomy_config` (stp 0.90, write_off_auto 500, dual_checker 10000, expiry hours 24), `output_hash_spec` (SHA256, `amount_format: 2dp`, `quantity_format: 6dp`).
- Keep `validate_and_repair()` deterministic-repair approach; update repairs for v2 defaults.
- Models — extend/rename existing six + add: `User`, `MatchLedger` (append-only), `GovernanceAction` (with `CheckConstraint("maker_id != checker_id OR checker_id IS NULL")`), `JournalEntry`, `RegulatoryNotification`, `CassReconciliation`, `LoopASuggestion` (formalize what Loop A proposals currently store), extend `Break` (side, archetype, causal_origin, field_most_responsible, root_cause_tree JSON, regulatory_narrative, autonomy_route, regulatory_escalation_required, age_business_days, quantity/amount NUMERIC columns), extend `Run` (position_proof_status, regulatory_escalation_count, match_rate NUMERIC(5,2), duration_ms), extend `ResolutionMemory` (+usage_count, last_used_at, causal_origin), keep `AuditLog` append-only.
- **All monetary/quantity columns become `Numeric(20,6)`** — Law 2.
- Indexes per spec (break: run_id/status/archetype/regulatory/isin; ledger: run_id; governance: break_id/status; audit: actor_id/timestamp; memory: archetype/causal_origin).
- New `Settings`: `SECRET_KEY`, `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_HOURS=24`, `CASS_SHORTFALL_THRESHOLD_EUR=1000`, `EMIR_AMOUNT_THRESHOLD_EUR=15000000`, `EMIR_DAYS_THRESHOLD=15`, `WRITE_OFF_AUTO_APPROVE_BELOW=500`, `WRITE_OFF_DUAL_CHECKER_ABOVE=10000`, `PENDING_APPROVAL_EXPIRY_HOURS=24`, `SUBSET_SUM_MAX_GROUP_SIZE=4`, `SUBSET_SUM_MAX_ROWS_PER_PARTITION=50`, `SUBSET_SUM_TIMEOUT_SECONDS=30`. Mirror into `.env.example`/`.env`.
**Acceptance:** `test_config_schema.py` rewritten for v2 (valid config passes; repairs exercised; SUPERSEDED lifecycle validated). App boots against recreated Postgres.

### P3 — Engine v2 — ✅ DONE 2026-07-22
> **Status notes:** new modules in `backend/app/engine/`: `transforms.py`
> (registry, all 11 v2 ops, null-safe), `business_days.py`, `aux.py`,
> `subset_sum.py` (group-size/partition/timeout guards), `position_proof.py`,
> `matching.py` (`MatchingWaterfall` — ONE_TO_ONE/ONE_TO_MANY/MANY_TO_ONE/
> N_TO_M_SUBSET_SUM/CASS_SPECIFIC, Decimal value rules, business-day date
> tolerance, `restrict_isins` scoping), `hashing.py` (row-ids + canonical
> `.2f`/`.6f` sorted match hash), `runner.py` (`reconcile()` full pipeline).
> Seed resolves exactly per the acceptance table: matched 14 (pass counts
> 5/2/1/1/1/2/2), open breaks 9 (2 duplicate_entry both sides, TRD008–011 drift
> @3 business-days, TRD021 account misbooking, TRD022 EMIR mv delta 300000,
> TRD019 missing leg), TRD024 CORPORATE_ACTION explained (excluded from open),
> position proof A=PROVED / B=NOT_APPLICABLE. Reproducibility verified on host
> and in the container — identical SHA-256. `test_engine.py` rewritten (30
> assertions incl. unit tests for business days / subset sum / transforms /
> Decimal tolerance); new standalone `test_reproducibility.py`. Backend suite:
> 56 passing / 16 known-red (test_api, now owned by P4+P8).
> **User-approved design decisions (2026-07-22):** (1) pass 6 vs 7 separated by
> an optional per-pass `restrict_isins` (added to the schema + passes 5/6/7 in
> the seed config); (2) duplicates handled by pre-match dedup with the surplus
> flagged `duplicate_entry` on each side; (3) TRD024 resolved as a
> position-control explained break (config has no corporate_action_adjust
> transform — it is implemented as an available op but unused by this seed).
> **Additional refinement (documented):** passes 1/2 gained a
> `computed_market_value` EXACT rule and pass 3 a rounding-scale (5.0) mv
> tolerance, so TRD013 falls correctly to pass 4 and TRD022's price dispute is
> NOT silently matched away.
> **Correction to earlier note:** the 16 known-red test_api tests are fixed in
> P4+P8 (API/service rewire to v2 + JWT), NOT in P3 — the engine gate is
> independent of the API layer.

### P3 (original spec) — Engine v2: Decimal, transforms, position proof, 7-pass waterfall, hash spec
**Goal:** the core. Everything deterministic, pandas-only.
**Files:** `backend/app/engine/{transforms,matching,hashing,runner}.py` (heavy rewrite), new `backend/app/engine/{position_proof,subset_sum,business_days,aux.py}` (aux loader).
- `transforms.py`: registry pattern keyed by op name; ops = existing 5 + `sign_flip(condition: dr_cr==CR)`, `strip_leading_zeros`, `date_normalise(input_format→%Y-%m-%d)`, `compute_market_value(quantity_col*price_col→output_col)`, `enrich_from_aux(aux alias, join_column, add columns)`, `corporate_action_adjust(corporate_actions aux: if ISIN has event with ex_date ≤ run date, multiply quantity by ratio)`. Null-safe everywhere (`pd.to_numeric(errors='coerce')`); never crash on NaN.
- `business_days.py`: business-day delta between two dates minus `market_holidays` rows for the configured market (default TARGET2) and weekends.
- `position_proof.py`: `verify(df, side_config, aux, run_date)` → `{side, status: PROVED|PARTIAL|UNPROVED, opening, computed_closing, stated_closing, variance, unexplained_variance}`; explained categories CORPORATE_ACTION and PENDING_SETTLEMENT reduce unexplained variance.
- `subset_sum.py`: `SubsetSumMatcher(max_group_size 4/4, max_rows_per_partition 50, timeout 30s)` using `itertools.combinations`, greedy first-match-wins, partition by ISIN, guards log-and-skip.
- `matching.py` → `MatchingWaterfall`: `execute(side_a, side_b)` assigns row_ids (sha256 of pipe-joined row values; `_1`,`_2` suffix dedup), then runs configured passes over shrinking pools; per-pass stats `{pass_number, pass_name, match_type, matched_count, pool_a_remaining, pool_b_remaining}`. Pass handlers: one_to_one (composite-key merge + value rules), one_to_many (group+aggregate B), many_to_one (mirror), n_to_m (subset-sum), cass_specific (liability vs safeguarded, shortfall detect). Value rules: EXACT (string equality), NUMERIC_TOLERANCE (`Decimal` diff ≤ tol), ASYMMETRIC_TOLERANCE (min ≤ a−b ≤ max), DATE_TOLERANCE (business-day aware). None/NaN → rule fails, never raises.
- `hashing.py`: canonical row per match = pipe-joined `[pass_number, isin, match_type, qty_a:.6f, qty_b:.6f, amt_a:.2f, amt_b:.2f, qty_var:.6f, amt_var:.2f]`, sorted, `\n`-joined, sha256. **Formatting laws 2–4 live here and in rule comparisons.**
- `runner.py` orchestrates: aux load → transforms → position proof (both sides) → waterfall → residuals become breaks (with side, pass_that_failed, variances) → duplicate/zero-qty handling (zero-qty rows dropped pre-match, logged) → hash.
**Acceptance (the critical gate):** new `backend/tests/test_engine.py` asserts against seed v2: Pass1 matches TRD001–005; Pass2 TRD006–007; Pass3 TRD012; Pass4 TRD013; Pass5 TRD014 (2 B-rows consumed); Pass6 TRD015+016; Pass7 TRD017+018; breaks = TRD008–011 (drift), TRD019 (missing leg), duplicate pair flagged, TRD021 (misbooking), TRD022 (EMIR-flaggable); TRD024 explained by corporate action in position proof; **reproducibility: two runs → identical hash** (`test_reproducibility.py`, runnable standalone: `python3 backend/tests/test_reproducibility.py` printing PASS + hash).

### P4 — JWT auth + roles — ✅ DONE 2026-07-22
> **Status notes:** `backend/app/auth.py` — bcrypt password hashing (direct, not
> passlib, to avoid its bcrypt-version fragility), PyJWT HS256 tokens from
> settings, `get_current_user` (Bearer header) + `require_role(*roles)`
> dependencies, 5 demo users (maker/checker/admin/client/dsi) + idempotent
> `seed_demo_users`. `routers/auth.py`: `POST /api/auth/login`, `GET /api/auth/me`,
> `GET /api/auth/probe-maker` (role-gate demo/test hook). `main.py` seeds users at
> startup and swaps the actors router for the auth router. Deleted
> `routers/actors.py`. **Kept `app/actors.py`** — the v1 config/run/break/loop
> routers still import `is_valid_actor`; deleting it would break boot. Frontend:
> `context/AuthContext.tsx` (localStorage token, `useAuth`, + a `useActor` compat
> shim so the v1 pages compile unchanged), `pages/LoginPage.tsx`, `api.ts` Bearer
> header + 401→logout hook, `App.tsx` login gate (all hooks before the gate — a
> Rules-of-Hooks bug was caught in the browser and fixed), `Sidebar.tsx` shows
> user email + role chip + logout. `test_auth.py` (14 tests: login all 5 roles,
> wrong pw 401, require_role 403/401, /me, actors-removed 404). Deps added:
> `pyjwt==2.10.1`, `bcrypt==4.2.1`. Verified live in the browser: login (Maker +
> Checker), role chip updates, logout returns to the gate. Suite: 70 passing / 16
> known-red.
> **P4/P8 boundary decision (documented, not asked — obvious non-wasteful
> reading):** P4 delivered auth infrastructure + login only. Per-endpoint role
> gates and actor-from-token on the config/run/break/loop endpoints are deferred
> to P8, where those endpoints are rebuilt for v2 — retrofitting them now, then
> again in P8, would be pure waste. So the 16 known-red test_api tests still use
> the v1 actor_id flow and remain red until P8.
> **Deferred to P9 (frontend rebuild):** sidebar still reads "ReconForge" and the
> Configure/Run pages are the v1 flow (functionally dead since P1); only the auth
> shell (login gate + user/role/logout) is new in P4.

### P4 (original spec) — JWT auth + roles (replaces "acting as")
**Files:** new `backend/app/auth.py` (create_access_token / verify_token / `get_current_user` / `require_role(*roles)` via PyJWT or python-jose + passlib[bcrypt]); new `backend/app/routers/auth.py` (`POST /api/auth/login`); `main.py` startup seeds 5 demo users (maker@db.com/maker123/MAKER, checker@db.com/checker123/CHECKER, admin@db.com/admin123/ADMIN, client@alphacapital.com/client123/CLIENT, dsi@db.com/dsi123/DSI); retire `actors.py` + `/api/actors` (delete router, remove `actor_id` request fields — actor now comes from the token).
**Frontend:** `context/ActorContext.tsx` → `context/AuthContext.tsx` (token in localStorage, axios-style interceptor in `api.ts` adding `Authorization: Bearer`, 401 → logout); new `pages/LoginPage.tsx` (demo creds listed); `Sidebar.tsx` shows user email + role chip + logout instead of the actor dropdown; role-gate nav items.
**Acceptance:** login works for all 5 users; wrong password → 401; MAKER-only endpoints reject CHECKER (403); existing flows still pass with tokens; add `test_auth.py`.

### P5 — Governance service — ✅ DONE 2026-07-22
> **Status notes:** `backend/app/services_governance.py` + `routers/governance.py`.
> `maker_submit` (break must be open → PENDING GovernanceAction, expires_at =
> now+24h, break → PENDING_CHECKER_APPROVAL, audit). `checker_approve` (maker≠
> checker enforced with a clean 400 AND the DB CheckConstraint as backstop;
> expiry check reopens the break; WRITE_OFF > `write_off_dual_checker_above`
> [10k] → 400 "requires a second checker"; approve of an accounting action
> [WRITE_OFF/FORCE_MATCH] → break RESOLVED_APPROVED + EXPORT-ONLY JournalEntry
> [audit_reference = sha256(action_id|checker_id|timestamp)] + resolution-memory
> write; FORCE_MATCH also writes a ManualMatch so Loop A keeps its signal;
> reject → break back to open). `expire_pending_actions` sweep runs on GET
> /pending. Autonomy: a WRITE_OFF below `write_off_auto_approve_below` [500]
> auto-approves at submit time via the `STP_AUTO` checker sentinel (≠ any numeric
> user id, so maker≠checker holds). Routes: maker-submit (MAKER), checker-approve
> (CHECKER), pending (CHECKER, w/ time_remaining), audit (any auth, paginated) —
> the first real consumers of P4's `require_role`, actor sourced from the JWT.
> `test_governance.py` (10 tests: happy path + journal, self-approval blocked at
> API and by DB constraint, >10k blocked, small-write-off auto-approve, reject
> reopens, expiry reopens, pending+audit, role gates). Suite 80/16 known-red.
> Verified live in the container: full submit→approve→journal e2e plus
> 401/403/404/200 gating.
> **Design decisions (documented):** INVESTIGATE / AWAIT_COUNTERPARTY are
> workflow-only — approving them records the decision + audit but does NOT post a
> journal entry and leaves the break open (only WRITE_OFF/FORCE_MATCH are
> accounting actions that resolve + post). Break "open" state is lowercase
> (matches the P3 engine output); governance transitions use the v2 uppercase
> states (PENDING_CHECKER_APPROVAL / RESOLVED_APPROVED). Governance methods are
> sync (not async as the PDF shows) per the locked sync-SQLAlchemy stack.
> Breaks are seeded directly in the test (run→break persistence is P8).

### P5 (original spec) — Governance service (break actions, journal entries)
**Files:** new `backend/app/services_governance.py` (or extend `services.py`), new `backend/app/routers/governance.py`.
- `maker_submit(break_id, action_type ∈ FORCE_MATCH|WRITE_OFF|INVESTIGATE|AWAIT_COUNTERPARTY, notes)` — break must be OPEN; creates PENDING GovernanceAction, `expires_at = now + 24h`; break → PENDING_CHECKER_APPROVAL; audit.
- `checker_approve(action_id, approved, notes)` — enforce maker≠checker (400) *and* rely on the DB CheckConstraint; expiry check; WRITE_OFF amount > 10,000 → 400 "Requires second checker"; WRITE_OFF < 500 may auto-approve per autonomy config; on approve → break RESOLVED_APPROVED + journal entry generated (export-only, `audit_reference = sha256(action_id+checker_id+timestamp)`) + write resolution memory; on reject → break back to OPEN.
- `expire_pending_actions()` — sweep on `GET /api/governance/pending`.
- Routes: maker-submit (MAKER), checker-approve (CHECKER), pending list w/ time_remaining (CHECKER), paginated `/api/governance/audit`.
- FORCE_MATCH resolutions must also write a `ManualMatch`-equivalent signal so Loop A keeps working (map: FORCE_MATCH ≈ today's manual match).
**Acceptance:** `test_governance.py`: full maker→checker happy path creates journal entry; self-approval blocked at API *and* by DB constraint; >10k write-off blocked; expiry flips break back to OPEN.

### P6 — Regulatory services — ✅ DONE 2026-07-22
> **Status notes:** `services_regulatory.py` + `routers/regulatory.py`.
> `screen_breaks_for_emir(db, breaks, run_date=, aux_data=)` — EUR-converts each
> break's amount via fx_rates; if EUR > `emir_amount_threshold_eur` (15M) AND age
> > `emir_days_threshold` (15 business days) → sets
> `break.regulatory_escalation_required` + `regulatory_narrative`, creates a DRAFT
> `RegulatoryNotification` (EMIR_ARTICLE_15, competent_authority default BaFin),
> audits. Age = `break.age_business_days` if set, else computed from row_a
> settlement_date → run_date (the runner sets it in P8; tests set it directly —
> the spec's "synthetic age"). `approve_emir_notification` DRAFT→FILED (records
> approved_by/at + filed_at, audits). `cass_daily(date)` — per-account
> liability vs safeguarded from cass_safeguarded.csv, aggregate shortfall (ACC002
> = 5,000 EUR in the seed), SHORTFALL_DETECTED when > `cass_shortfall_threshold`
> (1000), hashed resolution pack, idempotent per date (returns the existing row).
> `cass_resolution_pack(date)` — stable-hash JSON (sorted keys) with per-account
> breakdown + document_hash. Routes: EMIR list/approve (CHECKER|DSI), CASS
> daily + resolution-pack (CHECKER|DSI), CSDR → `[]` (deliberately minimal).
> `test_regulatory.py` (8 tests: large+aged break flagged & drafted, small/recent
> not flagged, list+approve files+audits, role gates, CASS shortfall detection,
> CASS idempotency, resolution-pack hash stability, CSDR empty). Suite 88/16.
> Verified live in the container.
> **Design decision (documented):** the EMIR draft narrative is generated by a
> deterministic template inside the service (the offline-stub posture — default
> `LLM_PROVIDER=stub`), NOT via a new LLM-interface method; a real-LLM narrative
> can be layered in during P7 without changing the flow. `regulatory_regime` was
> not added to the Break model (the regime lives on RegulatoryNotification).
> The post-run EMIR hook is a callable (`screen_breaks_for_emir`) that P8's run
> flow will invoke after persisting breaks; P6 drives it directly from tests.

### P6 (original spec) — Regulatory services (EMIR, CASS; CSDR minimal)
**Files:** new `backend/app/services_regulatory.py`, new `backend/app/routers/regulatory.py`.
- Post-run hook (in runner service): for each break compute EUR amount via `fx_rates`; if `> EMIR_AMOUNT_THRESHOLD_EUR` and `age_business_days > EMIR_DAYS_THRESHOLD` (seed the TRD022 break with a synthetic age so the demo fires, e.g. age from run_date vs settlement_date) → `regulatory_escalation_required=True`, create DRAFT `RegulatoryNotification` (regime EMIR_ARTICLE_15, competent_authority, LLM-drafted narrative via provider w/ deterministic stub fallback).
- CASS: `cass_daily(date)` — read `cass_safeguarded.csv`, compare client_liability vs safeguarded per account (ACC002 has a 5,000 shortfall in seed); shortfall > threshold → SHORTFALL_DETECTED + CassReconciliation row + resolution-pack JSON (hashed).
- Routes: EMIR list/approve (CHECKER|DSI, DRAFT→FILED w/ audit), CASS daily + resolution pack (CHECKER). CSDR: return an empty typed list (UI tab renders "no penalties") — explicitly minimal.
**Acceptance:** `test_regulatory.py`: TRD022 break gets flagged + draft notification; CASS daily detects the ACC002 5,000 shortfall; approve path audits.

### P7 — Agent layer v2 — ✅ DONE 2026-07-22
> **Status notes:** `engine/archetype.py` fully rewritten to the v2 deterministic
> classifier: 12 archetypes (settlement_date_drift, quantity_rounding,
> fx_price_rounding, one_to_many_split, many_to_one_aggregate, nm_subset_group,
> missing_leg, duplicate_entry, account_misbooking, emir_amount_dispute,
> corporate_action_adjustment, cass_shortfall), 9 causal origins,
> field_most_responsible, confidence, and a 3-layer root_cause_tree
> (data_layer / rule_that_failed / ai_diagnosis). Pure — no LLM, no DB — so runs
> stay reproducible; ARCHETYPE_LABELS kept (services.py uses it). New
> `app/agents.py`: `sme_analyze` (classifier + resolution-template prose +
> Loop B `retrieve_similar_cases` few-shot which bumps usage_count/last_used_at +
> `refuse_to_classify` when confidence < 0.65); `judge_route` **code-enforced**
> bands — regulatory flag → REGULATORY_ESCALATION (wins over confidence); <0.65 →
> ESCALATE_SENIOR; ≥ `stp_threshold` (0.90) → STP_AUTO_RESOLVE; else
> MAKER_REVIEW_REQUIRED; `detect_loop_a_pattern` (date-drift ≥4 same delta, or
> qty-rounding ≥4 sub-unit) + `propose_loop_a_change` (widen DATE_TOLERANCE,
> **capped at 5 days** with a note, semver minor-bump 1.0.0→1.1.0, status DRAFT,
> deepcopy-isolated so the source config isn't mutated; proposal re-validates
> clean). `test_agents.py` (18 tests) drives the real seed breaks: drift →
> settlement_date_drift + SETTLEMENT_TIMING_LAG + populated tree; TRD022 →
> REGULATORY_ESCALATION regardless of its 0.90 confidence; missing_leg (0.60) →
> refuse + ESCALATE_SENIOR; Loop A on 4 drift matches proposes 2→3 (and clamps a
> 7-day drift to 5). Suite 106/16. Verified in-container.
> **Design decisions (documented):** the classifier is the deterministic source
> of truth for archetype/causal/tree (offline-stub posture, default provider);
> a real LLM can enrich the *prose* later without changing routing or
> classification. P7 does NOT touch the P3 runner (it keeps its coarse hints);
> classification is applied at the agent/analyze layer, which P8 wires into the
> break-analyze endpoint. No new routes in P7 — the agents are pure functions.

### P7 (original spec) — Agent layer v2 (SME, Judge, Loop A caps, Loop B retrieval)
**Files:** `backend/app/llm/{base,stub,gemini,openai_compat}.py`, `backend/app/services.py` (advise path), `backend/app/engine/archetype.py`.
- Archetypes → 12: `settlement_date_drift`, `quantity_rounding`, `fx_price_rounding`, `one_to_many_split`, `many_to_one_aggregate`, `nm_subset_group`, `missing_leg`, `duplicate_entry`, `account_misbooking`, `emir_amount_dispute`, `corporate_action_adjustment`, `cass_shortfall`. Deterministic classifier maps pass_that_failed + deltas + regulatory flags → archetype (keep the no-LLM-fallback property).
- Causal origins (9, from spec): SETTLEMENT_TIMING_LAG, UPSTREAM_ETL_TRUNCATION, COUNTERPARTY_FEE_DEDUCTION, LEGAL_ENTITY_MISBOOKING, FX_RATE_SOURCE_DIVERGENCE, PARTIAL_SETTLEMENT, CORPORATE_ACTION_PROCESSING_LAG, PRICING_SOURCE_MISMATCH, SYSTEM_REPLAY.
- SME output gains: `causal_origin`, `field_most_responsible`, `root_cause_tree` = `{data_layer, rule_that_failed, ai_diagnosis}`, `regulatory_narrative`, `refuse_to_classify=True` when confidence < 0.65. Few-shot: top-3 `retrieve_similar_cases(archetype, causal_origin)` from resolution memory (bump usage_count/last_used_at).
- Judge: LLM recommends, **code enforces** routing: confidence <0.65 → ESCALATE_SENIOR; regulatory flag → REGULATORY_ESCALATION (always wins); ≥0.90 → STP_AUTO_RESOLVE (break → RESOLVED_STP + memory write source=STP_AUTO); else MAKER_REVIEW_REQUIRED.
- LLM-unavailable fallback returns the spec's shape (`refuse_to_classify: true`, route MAKER_REVIEW_REQUIRED) — wired through existing ladder.
- Loop A v2: pattern detectors over FORCE_MATCH resolutions of recent runs — date drift (4+ same date_delta), qty rounding (4+ variance <2), reference truncation (4+ same edit-distance); cap DATE_TOLERANCE ≤ 5 days (reject/clamp with note); what-if dry-runs candidate config; approval semver-bumps (1.0.0→1.1.0), old config → SUPERSEDED, audit.
**Acceptance:** `test_agents.py` (stub provider): drift break → settlement_date_drift + SETTLEMENT_TIMING_LAG + tree populated; TRD022 → REGULATORY_ESCALATION regardless of confidence; low-confidence → refuse + ESCALATE_SENIOR; Loop A on the 4 drift breaks proposes 2→3 days, never >5.

### P8 — API completion + client portal — ✅ DONE 2026-07-22
> **Status notes:** the keystone phase — rewired P1–P7 into a working v2 API and
> cleared the known-red set. New `services_run.py`: `execute_run` (P3 engine →
> persists Run + Breaks[open + explained] + MatchLedger, position-proof status,
> then P6 `screen_breaks_for_emir`), `reproduce`, `analyze_run_breaks` (P7
> SME+Judge over open breaks; STP band auto-resolves to RESOLVED_STP + memory,
> regulatory → PENDING_REGULATORY_ACTION, else routed/open), Loop A
> detect/propose (semver-bumped PENDING_APPROVAL config + LoopASuggestion) /
> what-if. Routers rewritten for v2 + JWT roles: `configs` (author→submit→
> approve/reject, `/versions`, prior APPROVED → SUPERSEDED on re-version, maker≠
> checker), `runs` (execute[MAKER; seed/upload], reproduce [+/reproducibility-
> check alias], position-proof, waterfall, summary, breaks, dashboard),
> `breaks` (analyze[MAKER], `/run/{id}` with status/archetype/regulatory_only
> filters, `/regulatory`[CHECKER|DSI]), `loops` (Loop A aggregate/propose/what-if,
> Loop B `/resolution-memory`). New `routers/client.py` (CLIENT: upload → run vs
> bank IBOR filtered by fund, simplified recon [plain-English issue labels],
> evidence pack with stable `document_hash` over the facts, isolation via
> Run.client_id). Model: Run gained `client_id` + `is_client_run`. `services.py`
> trimmed to shared helpers (audit + CSV/file I/O); **`app/actors.py` deleted**.
> Stub `summarize_config` made v2-aware. `test_api.py` rewritten as a 20-step v2
> e2e (author→approve→run→reproduce→proof/waterfall→analyze→governance force-match
> →Loop A propose/what-if/approve→client portal + isolation + evidence hash).
> **Result: 124 passing / 0 known-red** — the 16 v1 reds are gone. Verified live
> in-container (full flow + client portal + hash stability + 403 isolation).
> **Design decisions (documented):** offline (stub) config authoring degrades to
> the pre-approved seed recon (a real LLM authors from NL) — always schema-
> validated. EMIR age is computed from settlement_date → run_date (`date.today()`)
> so the ~2.5-year-old TRD022 dispute fires deterministically (only the >15M break
> qualifies). The `/runs/{id}/breaks` endpoint returns all persisted breaks (open
> + explained); `break_count` / `/breaks/run/{id}?status=open` count the 9 open.
> **⚠ Frontend now stale against v2** (its api.ts calls removed v1 endpoints);
> still builds, but the running app needs **P9** to work.

### P8 (original spec) — API surface completion + client portal backend
**Files:** `backend/app/routers/{configs,runs,breaks,loops}.py` (extend), new `backend/app/routers/client.py`, `backend/app/schemas.py`.
- Configs: submit → PENDING_APPROVAL, approve/reject (CHECKER), `GET /configs/{id}/versions`.
- Runs: execute (MAKER; seed or upload), `POST /runs/{id}/reproduce` (re-run + hash compare → PASS/FAIL), `GET /runs/{id}/position-proof`, `/waterfall` (pass stats), `/summary`.
- Breaks: analyze batch (SME+Judge over run), get by id / by run w/ filters (status, archetype, regulatory_only), `GET /breaks/regulatory` (CHECKER).
- Client portal (CLIENT role): `POST /api/client/upload` (multipart file + fund_id → run against default approved config, side A = bank seed IBOR filtered by fund, side B = upload), `GET /api/client/recon/{run_id}` (simplified: match rate, break count, plain-English archetype labels), `GET /api/client/break/{id}`, `GET /api/client/evidence/{run_id}` → EvidencePack JSON `{run_id, match_rate, output_hash, position_proof_status, generated_at, document_hash=sha256(pack)}`. Client must only see their own runs (`client_id` on Run).
**Acceptance:** `test_api.py` extended: role gates verified per route; client isolation verified; evidence pack hash stable.

### P9 — Frontend v2 — ✅ DONE 2026-07-22
> **Status notes:** full frontend rebuild against the v2 API (bottle-green design
> system + `Figure` numerals kept). `types.ts` + `api.ts` rewritten for every v2
> endpoint (Bearer header, 401→logout); `AuthContext` cleaned (dropped the useActor
> shim). Role-based `Sidebar` (MAKER/CHECKER/ADMIN → internal nav; CLIENT → portal
> only; DSI → Regulatory) + `App.tsx` router with per-role default landing + page
> guard. New components: `PositionProofCard` (PROVED/PARTIAL/UNPROVED traffic light,
> Opening/+Movement/=Closing, truncated SHA-256 + copy, Reproduce → PASS/FAIL),
> `WaterfallChart` (hand-rolled stacked bars — no new deps), `RootCauseTree`
> (3-layer Data/Rule/AI boxes), `StatusChip`. Pages: Dashboard, Configure
> (author→submit→approve/reject + versions + JSON viewer), Breaks (FilterBar +
> analyze + drilldown w/ root-cause tree + regulatory narrative + 4 governance
> actions), Governance (checker queue w/ expiry countdown + audit log w/ before/
> after expand), Learning (Loop A propose/what-if/approve + Loop B memory),
> Regulatory (EMIR/CASS/CSDR tabs), ClientPortal (upload → big match-rate → stat
> boxes → simplified breaks → evidence download). All v1 pages/components deleted.
> `npm run build` clean. **Browser-verified live** across roles: login gate, MAKER
> dashboard (KPIs, PROVED proof, Reproduce "PASS — a control, not a guess", 7-pass
> waterfall), breaks analyze → routing (TRD022 → Regulatory escalation) → 3-layer
> root-cause tree + EMIR Article-15 narrative, role-gated nav (MAKER has no
> Regulatory), CLIENT sees only the portal.
> **Design decisions (documented):** WaterfallChart is hand-rolled (MUI Box bars)
> rather than adding recharts — keeps deps lean, matches the design system.
> match_rate is now a percentage (0–100) from the backend, displayed directly.
> Governance's maker-queue actions live on the Breaks drilldown (submit) + the
> Governance checker-queue (approve) rather than a duplicate maker-queue tab.

### P9 (original spec) — Frontend v2 (extend the existing MUI shell)
**Files:** `frontend/src/` — new pages + sidebar growth. Keep bottle-green design system, `Figure` mono numerals, existing chips/bars.
- `LoginPage.tsx` + `AuthContext` (P4). Role-based sidebar: MAKER/CHECKER/ADMIN see internal nav; CLIENT sees portal only; DSI sees Regulatory.
- `DashboardPage.tsx` (new landing after login): run control (config selector + execute), **PositionProofCard** (Opening | +Movement | =Closing, PROVED/PARTIAL/UNPROVED traffic light, variance, truncated SHA-256 + copy, Reproduce button → PASS/FAIL banner), **WaterfallChart** (stacked bars matched/remaining per pass; click filters breaks), 4 KPI cards (rows/matched/breaks/regulatory), top-5 breaks mini table.
- `RunStep.tsx` → absorb into Dashboard or keep as "Run & breaks" — **decision: keep existing Run & breaks page as the breaks board**, add FilterBar (archetype/status/regulatory/ISIN) and upgrade `BreakDrilldown.tsx` with the **3-layer root-cause tree** (Data layer / Rule layer / AI diagnosis boxes), regulatory narrative box, editable chaser email w/ copy, resolution-memory badge ("Resolved as X n times — avg confidence"), role-based action buttons (MAKER: 4 governance actions; CHECKER: approve/reject).
- `GovernancePage.tsx`: tabs Maker queue (OPEN breaks + action buttons + confirm dialog) | Checker queue (PENDING actions, countdown to expiry, red <1h, self-approval disabled w/ tooltip) | Audit log (move existing AuditStep here, add pagination + before/after expand).
- `LearningPage.tsx`: evolve `LoopAStep` — suggestion cards w/ before/after diff, what-if metrics, cap note, approve/reject; Loop B stats (counts, top archetypes, retrievals table).
- `RegulatoryPage.tsx`: EMIR tab (notifications, red >15M/>15d, expandable draft, approve/file), CASS tab (liability vs safeguarded card, shortfall red, resolution-pack download), CSDR tab (empty-state table).
- `ClientPortalPage.tsx`: minimal layout (no internal sidebar): upload zone + fund selector → big match-rate figure, 3 stat boxes, simplified breaks table, evidence-pack download (JSON w/ hash shown).
- `ConfigureStep.tsx`: keep upload-first flow; add config JSON viewer/editor toggle, status badge incl. PENDING_APPROVAL/SUPERSEDED, version history table.
**Acceptance:** `npm run build` clean; browser-verified click-through of: login as maker → dashboard run → position proof PROVED → waterfall shows 7 passes → breaks board root-cause tree → governance submit → login as checker → approve → journal entry visible → learning approves drift suggestion → re-run improves match rate → regulatory tabs populated → client portal upload round-trip. (Use the Browser pane per repo conventions.)

### P10 — Tests, packaging, README — ✅ DONE 2026-07-22 · **PLAN COMPLETE**
> **Status notes:** all suites were already consolidated and green (124 passing /
> 0 failing in one `pytest` run: config_schema, engine, reproducibility [also a
> standalone runner], seed, auth, governance, regulatory, agents, api e2e).
> docker-compose gained passthrough for every P2+ setting (SECRET_KEY +
> ACCESS_TOKEN_EXPIRE_HOURS, WRITE_OFF_*/PENDING_APPROVAL_EXPIRY_HOURS,
> EMIR_*/CASS_*, SUBSET_SUM_*), all with sane defaults; the Dockerfile's seed
> step now fails the build loudly instead of `|| true` (the generator
> self-checks every demo scenario). README fully rewritten for ReconOS: ASCII
> four-plane diagram, 5-command quick start, demo-users table, 8-step demo
> walkthrough ending on the Reproduce moment, reproducibility-runner
> instructions, API-docs link, architecture decisions, regulatory features,
> competitive position, project structure. Verified: container rebuilt with the
> new files (build-time seed check passed), health OK, env passthrough confirmed
> in-container, in-container reproducibility PASS (same `5cc8ff8d…` hash as
> host), 124 tests green, frontend build clean, live login + /docs 200.
> **Stretch NOT done (per plan, needs explicit user ask):** the DB yellow/navy
> re-skin — the app keeps the bottle-green design system.

### P10 (original spec) — Tests, packaging, README (+ optional DB-brand skin)
**Files:** `backend/tests/*` consolidation, `README.md`, `docker-compose.yml`, `backend/Dockerfile`, `.env.example`.
- Ensure suites: config_schema, engine (waterfall scenario table), reproducibility (standalone runner prints PASS + hash), seed, auth, governance, regulatory, agents, api, client. Target: all green in one `python3 -m pytest -q`.
- docker-compose: keep Postgres; add `SECRET_KEY` + new thresholds passthrough; (frontend containerization optional — dev via Vite is fine for the demo).
- README rewrite: quick start, demo users table, 8-step demo walkthrough ending with the Reproduce moment ("Same input, same output, every time…"), architecture decisions, regulatory features, reproducibility runner instructions.
- **Stretch (ask user first):** re-skin theme to DB yellow (#FFD700)/dark navy accents per PDF branding.
**Acceptance:** fresh clone → `cp .env.example .env` → `docker compose up -d` → `npm --prefix frontend install && npm --prefix frontend run dev` → full demo path works; reproducibility runner prints PASS.

---

## 5. Sequencing & dependency notes for the implementing session

- Order is P1→P10; P4 (auth) can swap with P3 if desired, but P5–P8 all require P4's `require_role`.
- **Hard gate:** do not start frontend (P9) until P3's reproducibility test passes — the PDF's "critical rule" and ours.
- P2 breaks the old seed/config/tests on purpose (schema v2); P1+P2+P3 land as one coherent unit before the API layer is touched. Old tests for removed behavior are rewritten, not deleted silently.
- Existing behaviors to preserve through the refactor: config validate/repair-on-fail (deterministic), stub-provider determinism, audit writes on every mutation, what-if never hides newly-broken keys.
- The old 10-archetype classifier and single-pass engine are replaced; keep `engine/archetype.py` as the deterministic classifier home (new taxonomy), keep `reconcile()`-style single entry point in `runner.py` so `services.py` orchestration changes stay small.
- Postgres is recreated freely during dev (`docker compose down -v`) — no data to preserve.
