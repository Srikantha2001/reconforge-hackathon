"""Regulatory services + endpoints (P6 acceptance).

- EMIR: a large, aged break (the TRD022 dispute) is flagged + gets a DRAFT
  notification; approve files it and audits.
- CASS: the daily reconciliation detects the seeded ACC002 5,000 EUR shortfall,
  with a stable resolution-pack hash.
- CSDR: empty typed list.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app import models
from app import services_regulatory as reg


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _token(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_break(*, amount, currency="EUR", age=0, isin="XS0149080666", key="EMIR-TEST"):
    db = SessionLocal()
    try:
        run = models.Run(config_id=1, config_version="1.0.0", output_hash="r" * 64, match_rate=0)
        db.add(run)
        db.flush()
        brk = models.Break(
            run_id=run.id, break_key=key, side="AB", isin=isin, currency=currency,
            row_a={"account_id": "ACC002", "settlement_date": "2024-01-15"},
            row_b={"account_id": "ACC002"},
            amount_a=amount, quantity_a=500, archetype="emir_amount_dispute",
            age_business_days=age, status="open",
        )
        db.add(brk)
        db.commit()
        return brk.id
    finally:
        db.close()


# --- EMIR -------------------------------------------------------------------
def test_large_aged_break_is_flagged_and_drafted(client):
    break_id = _make_break(amount=16_500_000.0, age=20)  # > 15M and > 15 days
    db = SessionLocal()
    try:
        brk = db.get(models.Break, break_id)
        created = reg.screen_breaks_for_emir(db, [brk], competent_authority="BaFin")
        assert len(created) == 1
        notif = created[0]
        assert notif.regime == "EMIR_ARTICLE_15"
        assert notif.status == "DRAFT"
        assert notif.dispute_days == 20
        assert float(notif.dispute_amount) == 16_500_000.0
        db.refresh(brk)
        assert brk.regulatory_escalation_required is True
        assert brk.regulatory_narrative
    finally:
        db.close()


def test_small_or_recent_break_not_flagged(client):
    # Big but recent (age below the day limit) and small but aged — neither qualifies.
    big_recent_id = _make_break(amount=16_500_000.0, age=3, isin="XS0149080666", key="X1")
    small_aged_id = _make_break(amount=417_000.0, age=30, isin="DE000BAY0017", key="X2")
    db = SessionLocal()
    try:
        breaks = [db.get(models.Break, big_recent_id), db.get(models.Break, small_aged_id)]
        created = reg.screen_breaks_for_emir(db, breaks)
        assert created == []
    finally:
        db.close()


def test_emir_list_and_approve_files(client):
    break_id = _make_break(amount=20_000_000.0, age=25, key="EMIR-FILE")
    db = SessionLocal()
    try:
        reg.screen_breaks_for_emir(db, [db.get(models.Break, break_id)])
    finally:
        db.close()

    checker = _token(client, "checker@db.com", "checker123")
    listing = client.get("/api/regulatory/emir", headers=_auth(checker))
    assert listing.status_code == 200
    drafts = listing.json()
    target = next(n for n in drafts if n["break_id"] == break_id)
    assert target["status"] == "DRAFT"

    approve = client.post(f"/api/regulatory/emir/{target['id']}/approve", headers=_auth(checker))
    assert approve.status_code == 200
    assert approve.json()["status"] == "FILED"
    assert approve.json()["approved_by"]

    # Audit trail recorded the filing.
    audit = client.get("/api/governance/audit?entity_type=regulatory_notification", headers=_auth(checker))
    assert any(e["action"] == "emir_notification_filed" for e in audit.json())


def test_emir_requires_checker_or_dsi(client):
    maker = _token(client, "maker@db.com", "maker123")
    assert client.get("/api/regulatory/emir", headers=_auth(maker)).status_code == 403
    dsi = _token(client, "dsi@db.com", "dsi123")
    assert client.get("/api/regulatory/emir", headers=_auth(dsi)).status_code == 200


# --- CASS -------------------------------------------------------------------
def test_cass_daily_detects_acc002_shortfall(client):
    checker = _token(client, "checker@db.com", "checker123")
    resp = client.get("/api/regulatory/cass/daily/2024-01-15", headers=_auth(checker))
    assert resp.status_code == 200
    body = resp.json()
    assert body["shortfall_amount"] == 5000.0
    assert body["shortfall_status"] == "SHORTFALL_DETECTED"
    assert body["client_liability_total"] == 9_300_000.0
    assert body["safeguarded_funds_total"] == 9_295_000.0
    assert len(body["resolution_pack_hash"]) == 64


def test_cass_daily_is_idempotent(client):
    checker = _token(client, "checker@db.com", "checker123")
    a = client.get("/api/regulatory/cass/daily/2024-02-01", headers=_auth(checker)).json()
    b = client.get("/api/regulatory/cass/daily/2024-02-01", headers=_auth(checker)).json()
    assert a["id"] == b["id"]  # second call returns the same row, not a new one


def test_cass_resolution_pack_hash_stable(client):
    checker = _token(client, "checker@db.com", "checker123")
    p1 = client.get("/api/regulatory/cass/resolution-pack/2024-01-15", headers=_auth(checker)).json()
    p2 = client.get("/api/regulatory/cass/resolution-pack/2024-01-15", headers=_auth(checker)).json()
    assert p1["document_hash"] == p2["document_hash"]
    assert p1["shortfall_eur"] == 5000.0
    acc2 = next(a for a in p1["accounts"] if a["client_account"] == "ACC002")
    assert acc2["shortfall_eur"] == 5000.0


# --- CSDR -------------------------------------------------------------------
def test_csdr_returns_empty_list(client):
    checker = _token(client, "checker@db.com", "checker123")
    resp = client.get("/api/regulatory/csdr", headers=_auth(checker))
    assert resp.status_code == 200
    assert resp.json() == []
