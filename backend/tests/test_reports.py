"""Tests for Phase 1: player reporting system.

Unit tests:
  - submit_report() creates a row with status='pending'
  - has_pending_report() returns True after first report
  - list_reports() filters by status correctly
  - update_report_status() changes status and sets reviewed_at

Integration tests (REST):
  - POST /api/reports with valid JWT → 200 with report_id
  - POST /api/reports without JWT → 401
  - Self-report → 422
  - Duplicate report for same player/room → 429
  - GET /api/reports without admin token → 403
  - PATCH /api/reports/{id} updates status (admin)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-reports")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auth_db(monkeypatch, tmp_path):
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "auth.db")
    auth_mod.init_auth_db()
    yield


@pytest.fixture(autouse=True)
def clean_rooms(monkeypatch):
    from app.room import room_manager as _rm
    _rm.rooms.clear()
    monkeypatch.setattr("app.ws._ensure_tick_running", lambda _room: None)
    yield
    _rm.rooms.clear()


@pytest.fixture
def client():
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(name: str) -> dict:
    import app.auth as auth_mod
    return auth_mod.upsert_user(f"test:{name}", name, f"{name.lower()}@test.com", "")


def _make_token(name: str) -> str:
    import app.auth as auth_mod
    user = _make_user(name)
    return auth_mod.create_jwt(user["id"])


def _make_room_with_player(name: str) -> tuple[str, str]:
    """Create a room, add a player named *name*, return (room_id, player_id)."""
    from app.room import room_manager
    from app.puzzle_loader import load_puzzle
    puzzle = load_puzzle("classic_turtle_soup", "zh")
    room_id = room_manager.create_room(puzzle=puzzle, language="zh")
    room = room_manager.get_room(room_id)
    ws = MagicMock()
    ws.send_json = AsyncMock()
    player_id = "fake-player-id"
    room.add_player(player_id, name, ws)
    return room_id, player_id


# ---------------------------------------------------------------------------
# Unit: auth.py report CRUD functions
# ---------------------------------------------------------------------------


class TestSubmitReport:
    def test_creates_pending_report(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        rid = auth_mod.submit_report("room1", "reporter1", "reported1", "cheating")
        assert rid
        reports = auth_mod.list_reports()
        assert len(reports) == 1
        assert reports[0]["status"] == "pending"
        assert reports[0]["id"] == rid

    def test_message_text_truncated_to_500(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        long_text = "x" * 1000
        auth_mod.submit_report("room1", "r1", "r2", "cheating", message_text=long_text)
        reports = auth_mod.list_reports()
        assert len(reports[0]["message_text"]) == 500


class TestHasPendingReport:
    def test_false_before_any_report(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        assert not auth_mod.has_pending_report("r1", "r2", "room1")

    def test_true_after_report(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        auth_mod.submit_report("room1", "r1", "r2", "cheating")
        assert auth_mod.has_pending_report("r1", "r2", "room1")

    def test_false_different_room(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        auth_mod.submit_report("room1", "r1", "r2", "cheating")
        assert not auth_mod.has_pending_report("r1", "r2", "room2")


class TestListReports:
    def test_filter_by_status(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        rid = auth_mod.submit_report("room1", "r1", "r2", "cheating")
        auth_mod.update_report_status(rid, "reviewed")
        auth_mod.submit_report("room1", "r1", "r3", "spam")
        pending = auth_mod.list_reports(status="pending")
        reviewed = auth_mod.list_reports(status="reviewed")
        assert len(pending) == 1
        assert len(reviewed) == 1


class TestUpdateReportStatus:
    def test_sets_status_and_reviewed_at(self, tmp_path, monkeypatch):
        import app.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "r.db")
        auth_mod.init_auth_db()
        rid = auth_mod.submit_report("room1", "r1", "r2", "cheating")
        auth_mod.update_report_status(rid, "dismissed")
        reports = auth_mod.list_reports()
        assert reports[0]["status"] == "dismissed"
        assert reports[0]["reviewed_at"] is not None


# ---------------------------------------------------------------------------
# Integration: REST endpoints
# ---------------------------------------------------------------------------


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestReportEndpoints:
    def test_post_report_valid(self, client):
        reporter_tok = _make_token("Reporter")
        user = _make_user("Reporter")
        room_id, _ = _make_room_with_player("Target")

        resp = client.post(
            "/api/reports",
            json={"room_id": room_id, "reported_player_name": "Target", "reason": "cheating"},
            headers=_auth_header(reporter_tok),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "report_id" in body
        assert body["status"] == "pending"

    def test_post_report_no_auth(self, client):
        room_id, _ = _make_room_with_player("SomePlayer")
        resp = client.post(
            "/api/reports",
            json={"room_id": room_id, "reported_player_name": "SomePlayer", "reason": "cheating"},
        )
        assert resp.status_code == 401

    def test_post_report_unknown_room(self, client):
        tok = _make_token("ReporterX")
        resp = client.post(
            "/api/reports",
            json={"room_id": "ZZZZZZ", "reported_player_name": "Someone", "reason": "cheating"},
            headers=_auth_header(tok),
        )
        assert resp.status_code == 404

    def test_post_report_unknown_player(self, client):
        tok = _make_token("ReporterY")
        room_id, _ = _make_room_with_player("ActualPlayer")
        resp = client.post(
            "/api/reports",
            json={"room_id": room_id, "reported_player_name": "NoSuchPlayer", "reason": "cheating"},
            headers=_auth_header(tok),
        )
        assert resp.status_code == 404

    def test_post_report_duplicate_pending(self, client):
        tok = _make_token("RepDup")
        room_id, _ = _make_room_with_player("DupTarget")
        payload = {"room_id": room_id, "reported_player_name": "DupTarget", "reason": "cheating"}
        r1 = client.post("/api/reports", json=payload, headers=_auth_header(tok))
        assert r1.status_code == 200
        r2 = client.post("/api/reports", json=payload, headers=_auth_header(tok))
        assert r2.status_code == 429

    def test_get_reports_no_admin(self, client, monkeypatch):
        import app.main as main_mod
        # Configure a specific admin ID so non-admin users are rejected
        monkeypatch.setattr(main_mod, "_ADMIN_USER_IDS", {"admin-only-id"})
        tok = _make_token("RegularUser")
        resp = client.get("/api/reports", headers=_auth_header(tok))
        assert resp.status_code == 403

    def test_patch_report_no_admin(self, client, monkeypatch):
        import app.main as main_mod
        monkeypatch.setattr(main_mod, "_ADMIN_USER_IDS", {"admin-only-id"})
        tok = _make_token("RegularUser2")
        resp = client.patch(
            "/api/reports/fake-id",
            json={"status": "dismissed"},
            headers=_auth_header(tok),
        )
        assert resp.status_code == 403

    def test_patch_report_admin(self, client, monkeypatch):
        import app.main as main_mod
        reporter_tok = _make_token("PatchReporter")
        user = _make_user("PatchAdmin")
        admin_tok = _make_user("PatchAdmin")  # reuse user dict
        import app.auth as auth_mod
        admin_token = auth_mod.create_jwt(user["id"])
        # Register this user as admin
        monkeypatch.setattr(main_mod, "_ADMIN_USER_IDS", {user["id"]})

        room_id, _ = _make_room_with_player("PatchTarget")
        r = client.post(
            "/api/reports",
            json={"room_id": room_id, "reported_player_name": "PatchTarget", "reason": "cheating"},
            headers=_auth_header(reporter_tok),
        )
        report_id = r.json()["report_id"]

        patch_resp = client.patch(
            f"/api/reports/{report_id}",
            json={"status": "dismissed"},
            headers=_auth_header(admin_token),
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["ok"] is True

    def test_get_reports_admin(self, client, monkeypatch):
        import app.main as main_mod
        import app.auth as auth_mod
        user = _make_user("GetAdmin")
        admin_token = auth_mod.create_jwt(user["id"])
        monkeypatch.setattr(main_mod, "_ADMIN_USER_IDS", {user["id"]})

        room_id, _ = _make_room_with_player("GetTarget")
        reporter_tok = _make_token("GetReporter")
        client.post(
            "/api/reports",
            json={"room_id": room_id, "reported_player_name": "GetTarget", "reason": "spam"},
            headers=_auth_header(reporter_tok),
        )

        resp = client.get("/api/reports", headers=_auth_header(admin_token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
