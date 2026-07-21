"""End-to-end API tests covering the CORE flow and both learning loops.

Uses a single sequential TestClient session (module scope) because the
workflow is inherently stateful: author -> approve -> run -> advise ->
manually match -> Loop A propose/what-if/approve -> Loop B resolve. This
mirrors the §12 demo script and exercises the maker-checker gate, the
reproducibility check, and the audit trail along the way.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.seed import SEED_DIR
from app.seed.generator import write_seed


@pytest.fixture(scope="module", autouse=True)
def ensure_seed():
    write_seed(SEED_DIR)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def actors(client):
    return client.get("/api/actors").json()


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unknown_actor_rejected(client):
    info = client.get("/api/seed/info").json()
    resp = client.post(
        "/api/configs/author",
        json={
            "nl_description": "match on trade id",
            "actor_id": "nobody",
            "columns_a": info["ledger_columns"],
            "columns_b": info["statement_columns"],
        },
    )
    assert resp.status_code == 400


class TestFullWorkflow:
    """Ordered steps sharing state via class attributes — deliberately
    sequential, matching how a human would actually operate the app."""

    config_id = None
    run_id = None
    loop_a_config_id = None

    def test_01_author_config(self, client, actors):
        alice = actors[0]["id"]
        info = client.get("/api/seed/info").json()
        assert info["exists"]

        resp = client.post(
            "/api/configs/author",
            json={
                "nl_description": (
                    "Match ledger to statement exactly on trade id, amount tolerance "
                    "of 0.01, within 2 days for value date, and account must match exactly"
                ),
                "actor_id": alice,
                "columns_a": info["ledger_columns"],
                "columns_b": info["statement_columns"],
            },
        )
        assert resp.status_code == 200, resp.text
        cfg = resp.json()
        assert cfg["status"] == "draft"
        assert cfg["author_id"] == alice
        assert cfg["english_summary"]  # §11 OPEN point 1: always present
        assert any(r["type"] == "exact" for r in cfg["config_json"]["match_rules"])
        TestFullWorkflow.config_id = cfg["id"]

    def test_02_self_approve_rejected(self, client, actors):
        alice = actors[0]["id"]
        resp = client.post(
            f"/api/configs/{TestFullWorkflow.config_id}/approve", json={"actor_id": alice}
        )
        assert resp.status_code == 403

    def test_03_run_before_approval_rejected(self, client, actors):
        alice = actors[0]["id"]
        resp = client.post(
            "/api/runs",
            data={"config_id": TestFullWorkflow.config_id, "actor_id": alice, "use_seed": "true"},
        )
        assert resp.status_code == 400

    def test_04_approve_by_different_actor(self, client, actors):
        bob = actors[1]["id"]
        resp = client.post(
            f"/api/configs/{TestFullWorkflow.config_id}/approve", json={"actor_id": bob}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        assert resp.json()["approver_id"] == bob

    def test_05_run_on_seed(self, client, actors):
        alice = actors[0]["id"]
        resp = client.post(
            "/api/runs",
            data={"config_id": TestFullWorkflow.config_id, "actor_id": alice, "use_seed": "true"},
        )
        assert resp.status_code == 200, resp.text
        run = resp.json()
        assert run["total_a"] == run["total_b"]
        assert run["matched_count"] + run["break_count"] >= run["total_a"]
        assert 0.0 < run["match_rate"] < 1.0
        TestFullWorkflow.run_id = run["id"]

    def test_06_reproducibility_check(self, client):
        resp = client.post(f"/api/runs/{TestFullWorkflow.run_id}/reproducibility-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["reproducible"] is True
        assert body["original_hash"] == body["recomputed_hash"]

    def test_07_dashboard_and_breaks(self, client):
        dash = client.get(f"/api/runs/{TestFullWorkflow.run_id}/dashboard").json()
        assert dash["run"]["id"] == TestFullWorkflow.run_id
        assert sum(dash["archetype_counts"].values()) == dash["run"]["break_count"]

        breaks = client.get(f"/api/runs/{TestFullWorkflow.run_id}/breaks").json()
        assert len(breaks) == dash["run"]["break_count"]
        found_archetypes = {b["archetype"] for b in breaks}
        # Every break already carries a deterministic archetype straight off the run.
        assert None not in found_archetypes

    def test_08_advise_and_chaser(self, client, actors):
        alice = actors[0]["id"]
        breaks = client.get(f"/api/runs/{TestFullWorkflow.run_id}/breaks").json()
        target = breaks[0]

        resp = client.post(f"/api/breaks/{target['id']}/advise", json={"actor_id": alice})
        assert resp.status_code == 200
        advice = resp.json()
        assert advice["judge_decision"] in ("accept", "route_to_human")
        assert 0.0 <= advice["sme_confidence"] <= 1.0

        resp = client.post(f"/api/breaks/{target['id']}/chaser", json={"actor_id": alice})
        assert resp.status_code == 200
        draft = resp.json()
        assert draft["to"] and draft["subject"] and draft["body"]

    def test_09_loop_a_manual_match_drift_cluster(self, client, actors):
        alice = actors[0]["id"]
        breaks = client.get(f"/api/runs/{TestFullWorkflow.run_id}/breaks").json()
        drift_breaks = [b for b in breaks if b["break_key"].startswith("DRF")]
        assert len(drift_breaks) == 5

        for b in drift_breaks:
            resp = client.post(f"/api/breaks/{b['id']}/manual-match", json={"actor_id": alice})
            assert resp.status_code == 200
            assert resp.json()["status"] == "resolved"

    def test_10_loop_a_aggregate(self, client):
        resp = client.get(f"/api/runs/{TestFullWorkflow.run_id}/loop-a/aggregate")
        assert resp.status_code == 200
        groups = resp.json()
        date_group = next(g for g in groups if g["type"] == "date_tolerance")
        assert date_group["count"] == 5
        assert all(d == 3 for d in date_group["observed_deltas"])

    def test_11_loop_a_propose(self, client, actors):
        alice = actors[0]["id"]
        groups = client.get(f"/api/runs/{TestFullWorkflow.run_id}/loop-a/aggregate").json()
        date_group = next(g for g in groups if g["type"] == "date_tolerance")

        resp = client.post(
            f"/api/runs/{TestFullWorkflow.run_id}/loop-a/propose",
            json={"actor_id": alice, **{k: date_group[k] for k in ("field_a", "field_b", "type")}},
        )
        assert resp.status_code == 200, resp.text
        proposal = resp.json()
        assert proposal["new_config"]["status"] == "draft"
        assert proposal["new_config"]["origin"] == "loop_a"
        new_rule = next(
            r for r in proposal["new_config"]["config_json"]["match_rules"] if r["type"] == "date_tolerance"
        )
        assert new_rule["tolerance_days"] == 3
        TestFullWorkflow.loop_a_config_id = proposal["new_config"]["id"]

    def test_12_what_if_before_approval(self, client):
        resp = client.post(
            f"/api/runs/{TestFullWorkflow.run_id}/loop-a/what-if",
            json={"candidate_config_id": TestFullWorkflow.loop_a_config_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["candidate_match_rate"] > body["current_match_rate"]
        assert len(body["newly_matched_keys"]) == 5
        assert body["newly_broken_keys"] == []  # governance: surfaced even if empty

    def test_13_loop_a_approve_same_gate(self, client, actors):
        alice, bob = actors[0]["id"], actors[1]["id"]
        # The proposal's author is the human who triggered Loop A (alice) —
        # same maker-checker gate as initial authoring.
        resp = client.post(
            f"/api/configs/{TestFullWorkflow.loop_a_config_id}/approve", json={"actor_id": alice}
        )
        assert resp.status_code == 403
        resp = client.post(
            f"/api/configs/{TestFullWorkflow.loop_a_config_id}/approve", json={"actor_id": bob}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_14_rerun_shows_improved_match_rate(self, client, actors):
        alice = actors[0]["id"]
        resp = client.post(
            "/api/runs",
            data={"config_id": TestFullWorkflow.loop_a_config_id, "actor_id": alice, "use_seed": "true"},
        )
        assert resp.status_code == 200
        new_run = resp.json()
        old_run = client.get(f"/api/runs/{TestFullWorkflow.run_id}").json()
        assert new_run["match_rate"] > old_run["match_rate"]

    def test_15_loop_b_resolve_and_memory(self, client, actors):
        alice = actors[0]["id"]
        breaks = client.get(f"/api/runs/{TestFullWorkflow.run_id}/breaks").json()
        fee_break = next(b for b in breaks if b["archetype"] == "fee_charge_diff")

        resp = client.post(
            f"/api/breaks/{fee_break['id']}/resolve",
            json={
                "actor_id": alice,
                "confirmed_archetype": "fee_charge_diff",
                "confirmed_resolution": "Confirmed legitimate service fee.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

        mem = client.get("/api/resolution-memory").json()
        assert any(m["archetype"] == "fee_charge_diff" for m in mem)

    def test_16_audit_log_has_full_trail(self, client):
        entries = client.get("/api/audit").json()
        actions = {e["action"] for e in entries}
        assert {
            "config_authored",
            "config_approved",
            "run_executed",
            "break_advised",
            "manual_match_recorded",
            "loop_a_proposed",
            "break_resolved",
        } <= actions
