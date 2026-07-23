"""Governance service + endpoints (P5 acceptance).

Breaks are created directly in the DB here (how breaks get persisted from a run
is P8); these tests exercise the governance workflow in isolation: maker submit
-> checker approve -> journal entry, self-approval blocked (API + DB
constraint), the >10k write-off ceiling, auto-approval of small write-offs, and
expiry reopening the break.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.db import SessionLocal
from app import models


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # lifespan seeds tables + demo users
        yield c


def _token(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]


@pytest.fixture
def maker_token(client):
    return _token(client, "maker@db.com", "maker123")


@pytest.fixture
def checker_token(client):
    return _token(client, "checker@db.com", "checker123")


def _make_break(amount=5000.0, status="open"):
    """Insert a run + open break with a given amount; return its id."""
    db = SessionLocal()
    try:
        run = models.Run(
            config_id=1, config_version="1.0.0", output_hash="x" * 64, match_rate=0,
        )
        db.add(run)
        db.flush()
        brk = models.Break(
            run_id=run.id,
            break_key=f"TESTBRK-{amount}",
            side="AB",
            isin="DE000BAY0017",
            currency="EUR",
            row_a={"account_id": "ACC002", "quantity": 100},
            row_b={"account_id": "ACC002", "quantity": 100},
            amount_a=amount,
            quantity_a=100,
            archetype="value_date_mismatch",
            status=status,
        )
        db.add(brk)
        db.commit()
        return brk.id
    finally:
        db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- Happy path -------------------------------------------------------------
def test_maker_submit_then_checker_approve_creates_journal(client, maker_token, checker_token):
    break_id = _make_break(amount=5000.0)

    submit = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "WRITE_OFF", "notes": "stale break"},
        headers=_auth(maker_token),
    )
    assert submit.status_code == 200, submit.text
    action = submit.json()["action"]
    assert action["status"] == "PENDING"
    assert submit.json()["journal_entry"] is None  # 5000 is above the auto-approve floor

    approve = client.post(
        "/api/governance/checker-approve",
        json={"action_id": action["id"], "approved": True, "notes": "agreed"},
        headers=_auth(checker_token),
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "APPROVED"
    je = body["journal_entry"]
    assert je is not None
    assert je["entry_type"] == "WRITE_OFF"
    assert je["amount"] == 5000.0
    assert je["debit_account"] == "RECON_WRITE_OFF_EXPENSE"
    assert len(je["audit_reference"]) == 64

    # Break is resolved.
    db = SessionLocal()
    try:
        assert db.get(models.Break, break_id).status == "RESOLVED_APPROVED"
    finally:
        db.close()


# --- maker != checker (API + DB constraint) --------------------------------
def test_self_approval_blocked_at_api(client, maker_token):
    # maker cannot even reach the CHECKER-gated endpoint (403).
    break_id = _make_break(amount=1000.0)
    submit = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "INVESTIGATE"},
        headers=_auth(maker_token),
    )
    action_id = submit.json()["action"]["id"]
    resp = client.post(
        "/api/governance/checker-approve",
        json={"action_id": action_id, "approved": True},
        headers=_auth(maker_token),  # a MAKER token on a CHECKER route
    )
    assert resp.status_code == 403


def test_same_person_maker_checker_blocked_in_service(client):
    # Directly drive the service with checker == maker -> clean 400.
    from app.services_governance import checker_approve
    break_id = _make_break(amount=1000.0)
    db = SessionLocal()
    try:
        action = models.GovernanceAction(
            break_id=break_id, action_type="INVESTIGATE", maker_id="7",
            status="PENDING", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(action)
        db.commit()
        action_id = action.id
    finally:
        db.close()

    from fastapi import HTTPException
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            checker_approve(db, action_id=action_id, checker_id="7", approved=True, notes=None)
        assert exc.value.status_code == 400
    finally:
        db.close()


def test_maker_equals_checker_rejected_by_db_constraint():
    db = SessionLocal()
    try:
        db.add(
            models.GovernanceAction(
                break_id=1, action_type="WRITE_OFF", maker_id="9", checker_id="9", status="APPROVED",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


# --- Write-off ceiling ------------------------------------------------------
def test_write_off_above_dual_checker_limit_blocked(client, maker_token, checker_token):
    break_id = _make_break(amount=50000.0)  # > 10,000
    action_id = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "WRITE_OFF"},
        headers=_auth(maker_token),
    ).json()["action"]["id"]

    resp = client.post(
        "/api/governance/checker-approve",
        json={"action_id": action_id, "approved": True},
        headers=_auth(checker_token),
    )
    assert resp.status_code == 400
    assert "second checker" in resp.json()["detail"].lower()


# --- Auto-approval of small write-offs --------------------------------------
def test_small_write_off_auto_approves(client, maker_token):
    break_id = _make_break(amount=100.0)  # < 500 auto-approve floor
    submit = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "WRITE_OFF"},
        headers=_auth(maker_token),
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["action"]["status"] == "APPROVED"
    assert body["action"]["checker_id"] == "STP_AUTO"
    assert body["journal_entry"] is not None

    db = SessionLocal()
    try:
        assert db.get(models.Break, break_id).status == "RESOLVED_APPROVED"
    finally:
        db.close()


# --- Rejection reopens the break -------------------------------------------
def test_rejection_reopens_break(client, maker_token, checker_token):
    break_id = _make_break(amount=3000.0)
    action_id = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "WRITE_OFF"},
        headers=_auth(maker_token),
    ).json()["action"]["id"]
    resp = client.post(
        "/api/governance/checker-approve",
        json={"action_id": action_id, "approved": False, "notes": "not a write-off"},
        headers=_auth(checker_token),
    )
    assert resp.status_code == 200 and resp.json()["status"] == "REJECTED"
    db = SessionLocal()
    try:
        assert db.get(models.Break, break_id).status == "open"
    finally:
        db.close()


# --- Expiry -----------------------------------------------------------------
def test_expiry_reopens_break_and_blocks_approval(client, checker_token):
    break_id = _make_break(amount=2000.0, status="PENDING_CHECKER_APPROVAL")
    db = SessionLocal()
    try:
        action = models.GovernanceAction(
            break_id=break_id, action_type="WRITE_OFF", maker_id="1", status="PENDING",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # already expired
        )
        db.add(action)
        db.commit()
        action_id = action.id
    finally:
        db.close()

    # The pending sweep flips it to EXPIRED and reopens the break.
    pending = client.get("/api/governance/pending", headers=_auth(checker_token))
    assert pending.status_code == 200
    assert action_id not in [a["id"] for a in pending.json()]

    db = SessionLocal()
    try:
        assert db.get(models.GovernanceAction, action_id).status == "EXPIRED"
        assert db.get(models.Break, break_id).status == "open"
    finally:
        db.close()


# --- Pending list + audit ---------------------------------------------------
def test_pending_list_and_audit_trail(client, maker_token, checker_token):
    break_id = _make_break(amount=4000.0)
    client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "AWAIT_COUNTERPARTY"},
        headers=_auth(maker_token),
    )
    pending = client.get("/api/governance/pending", headers=_auth(checker_token))
    assert pending.status_code == 200
    assert all("time_remaining_seconds" in a for a in pending.json())

    audit = client.get("/api/governance/audit?entity_type=governance_action", headers=_auth(maker_token))
    assert audit.status_code == 200
    assert any(e["action"] == "governance_maker_submit" for e in audit.json())


def test_maker_submit_requires_maker_role(client, checker_token):
    break_id = _make_break(amount=1000.0)
    resp = client.post(
        "/api/governance/maker-submit",
        json={"break_id": break_id, "action_type": "WRITE_OFF"},
        headers=_auth(checker_token),  # CHECKER on a MAKER route
    )
    assert resp.status_code == 403
