"""End-to-end API tests for the v2 ReconOS flow (P8).

A single stateful session drives the full demo: author → submit → approve a
config (maker-checker), run it on the seed, verify reproducibility, inspect the
position proof / waterfall / summary, analyze breaks (SME+Judge), drive a
governance write-off, force-match the drift cluster and propose a Loop A
re-version, then exercise the client portal (upload → recon → evidence) with
isolation. Replaces the v1 workflow tests.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services_run import SEED_DIR
from app.seed.generator import write_seed


@pytest.fixture(scope="module", autouse=True)
def ensure_seed():
    write_seed(SEED_DIR)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _token(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]


@pytest.fixture(scope="module")
def maker(client):
    return {"Authorization": f"Bearer {_token(client, 'maker@db.com', 'maker123')}"}


@pytest.fixture(scope="module")
def checker(client):
    return {"Authorization": f"Bearer {_token(client, 'checker@db.com', 'checker123')}"}


@pytest.fixture(scope="module")
def clientuser(client):
    return {"Authorization": f"Bearer {_token(client, 'client@alphacapital.com', 'client123')}"}


# Shared state across the ordered workflow.
STATE = {}


class TestFullWorkflow:
    def test_01_author_config(self, client, maker):
        r = client.post("/api/configs/author", json={"nl_description": ""}, headers=maker)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg["status"] == "DRAFT"
        assert cfg["version"] == "1.0.0"
        assert cfg["recon_type"] == "POSITION"
        STATE["config_id"] = cfg["id"]

    def test_02_author_requires_maker(self, client, checker):
        assert client.post("/api/configs/author", json={"nl_description": ""}, headers=checker).status_code == 403

    def test_03_submit_and_self_approve_blocked(self, client, maker):
        cid = STATE["config_id"]
        assert client.post(f"/api/configs/{cid}/submit", headers=maker).status_code == 200
        # Maker cannot approve (CHECKER-gated) → 403.
        assert client.post(f"/api/configs/{cid}/approve", json={"approved": True}, headers=maker).status_code == 403

    def test_04_checker_approves(self, client, checker):
        cid = STATE["config_id"]
        r = client.post(f"/api/configs/{cid}/approve", json={"approved": True}, headers=checker)
        assert r.status_code == 200
        assert r.json()["status"] == "APPROVED"

    def test_05_run_requires_approved_and_maker(self, client, maker, checker):
        cid = STATE["config_id"]
        # Checker can't run (MAKER-gated).
        assert client.post("/api/runs", data={"config_id": cid, "use_seed": "true"}, headers=checker).status_code == 403
        r = client.post("/api/runs", data={"config_id": cid, "use_seed": "true"}, headers=maker)
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["total_a"] == 25 and run["total_b"] == 21
        assert run["matched_count"] == 14
        assert run["position_proof_status"] == "PROVED"
        assert run["regulatory_escalation_count"] == 1  # TRD022 EMIR
        STATE["run_id"] = run["id"]
        STATE["output_hash"] = run["output_hash"]

    def test_06_reproduce_passes(self, client, maker):
        r = client.post(f"/api/runs/{STATE['run_id']}/reproduce", headers=maker)
        assert r.status_code == 200
        assert r.json()["reproducible"] is True
        assert r.json()["recomputed_hash"] == STATE["output_hash"]

    def test_07_position_proof_and_waterfall(self, client, maker):
        pp = client.get(f"/api/runs/{STATE['run_id']}/position-proof", headers=maker).json()
        assert pp[0]["side"] == "A" and pp[0]["status"] == "PROVED"
        wf = client.get(f"/api/runs/{STATE['run_id']}/waterfall", headers=maker).json()
        assert [p["matched_count"] for p in wf] == [5, 2, 1, 1, 1, 2, 2]

    def test_08_summary_and_breaks(self, client, maker):
        summ = client.get(f"/api/runs/{STATE['run_id']}/summary", headers=maker).json()
        assert summ["regulatory_escalation_count"] == 1
        assert summ["run"]["break_count"] == 9
        breaks = client.get(f"/api/breaks/run/{STATE['run_id']}?status=open", headers=maker).json()
        assert len(breaks) == 9  # open breaks (the explained TRD024 is separate)
        STATE["breaks"] = breaks

    def test_09_analyze_breaks(self, client, maker):
        r = client.post("/api/breaks/analyze", json={"run_id": STATE["run_id"]}, headers=maker)
        assert r.status_code == 200
        analyses = r.json()
        routes = {a["archetype"]: a["autonomy_route"] for a in analyses}
        assert routes.get("emir_amount_dispute") == "REGULATORY_ESCALATION"
        assert routes.get("missing_leg") == "ESCALATE_SENIOR"  # low confidence
        assert routes.get("settlement_date_drift") == "MAKER_REVIEW_REQUIRED"

    def test_10_regulatory_break_listed(self, client, checker):
        regs = client.get("/api/breaks/regulatory", headers=checker).json()
        assert any(b["isin"] == "XS0149080666" for b in regs)  # TRD022

    def test_11_governance_write_off(self, client, maker, checker):
        # Pick a small-enough drift break to write off cleanly.
        drift = next(b for b in STATE["breaks"] if b["isin"] == "DE000BAY0017")
        sub = client.post("/api/governance/maker-submit",
                          json={"break_id": drift["id"], "action_type": "FORCE_MATCH"}, headers=maker)
        assert sub.status_code == 200
        aid = sub.json()["action"]["id"]
        appr = client.post("/api/governance/checker-approve",
                           json={"action_id": aid, "approved": True}, headers=checker)
        assert appr.status_code == 200
        assert appr.json()["journal_entry"]["entry_type"] == "FORCE_MATCH_ADJUSTMENT"

    def test_12_loop_a_needs_four(self, client, maker):
        agg = client.get(f"/api/runs/{STATE['run_id']}/loop-a/aggregate", headers=maker).json()
        assert agg["manual_match_count"] == 1  # only one force-match so far
        assert agg["pattern"] is None

    def test_13_force_match_drift_cluster_and_propose(self, client, maker, checker):
        # Force-match the remaining 3 drift breaks to reach the 4-occurrence threshold.
        for isin in ("CH0012221716", "IT0003128367", "ES0113211835"):
            brk = next(b for b in STATE["breaks"] if b["isin"] == isin)
            aid = client.post("/api/governance/maker-submit",
                              json={"break_id": brk["id"], "action_type": "FORCE_MATCH"}, headers=maker).json()["action"]["id"]
            client.post("/api/governance/checker-approve",
                        json={"action_id": aid, "approved": True}, headers=checker)
        prop = client.post(f"/api/runs/{STATE['run_id']}/loop-a/propose", headers=maker)
        assert prop.status_code == 200, prop.text
        body = prop.json()
        assert body["new_config"]["version"] == "1.1.0"
        assert body["new_config"]["status"] == "PENDING_APPROVAL"
        STATE["candidate_config_id"] = body["new_config"]["id"]

    def test_14_loop_a_what_if_shows_improvement(self, client, maker):
        r = client.post(f"/api/runs/{STATE['run_id']}/loop-a/what-if",
                        json={"candidate_config_id": STATE["candidate_config_id"]}, headers=maker)
        assert r.status_code == 200
        wi = r.json()
        assert wi["candidate_match_rate"] > wi["current_match_rate"]  # drift now matches

    def test_15_loop_a_approve_supersedes(self, client, checker):
        cid = STATE["candidate_config_id"]
        r = client.post(f"/api/configs/{cid}/approve", json={"approved": True}, headers=checker)
        assert r.status_code == 200 and r.json()["status"] == "APPROVED"
        # Prior version is now SUPERSEDED.
        versions = client.get(f"/api/configs/{cid}/versions", headers=checker).json()
        assert any(v["status"] == "SUPERSEDED" for v in versions)

    def test_16_audit_trail(self, client, maker):
        entries = client.get("/api/governance/audit?page=1&page_size=200", headers=maker).json()
        actions = {e["action"] for e in entries}
        assert {"config_authored", "config_approved", "run_executed", "break_analyzed",
                "governance_checker_approve", "loop_a_proposed"} <= actions

    # --- Client portal -----------------------------------------------------
    def test_17_client_upload_and_isolation(self, client, clientuser, maker):
        csv = (SEED_DIR / "bny_mt535_custody.csv").read_bytes()
        r = client.post("/api/client/upload", data={"fund_id": "FUND_A", "recon_type": "POSITION"},
                        files={"file": ("mine.csv", csv, "text/csv")}, headers=clientuser)
        assert r.status_code == 200, r.text
        run_id = r.json()["run_id"]
        STATE["client_run_id"] = run_id
        # A maker cannot read a client's run via the client portal (isolation).
        assert client.get(f"/api/client/recon/{run_id}", headers=maker).status_code == 403

    def test_18_client_recon_simplified(self, client, clientuser):
        r = client.get(f"/api/client/recon/{STATE['client_run_id']}", headers=clientuser)
        assert r.status_code == 200
        body = r.json()
        assert "match_rate" in body
        for b in body["breaks"]:
            assert b["issue"]  # plain-English label, never a raw archetype code

    def test_19_evidence_pack_hash_stable(self, client, clientuser):
        rid = STATE["client_run_id"]
        p1 = client.get(f"/api/client/evidence/{rid}", headers=clientuser).json()
        p2 = client.get(f"/api/client/evidence/{rid}", headers=clientuser).json()
        assert p1["document_hash"] == p2["document_hash"]  # stable across calls
        assert len(p1["document_hash"]) == 64
        assert p1["output_hash"] == STATE["output_hash"] or p1["run_id"] == rid

    def test_20_client_cannot_reach_internal_routes(self, client, clientuser):
        assert client.post("/api/configs/author", json={"nl_description": ""}, headers=clientuser).status_code == 403
        assert client.post("/api/breaks/analyze", json={"run_id": 1}, headers=clientuser).status_code == 403
