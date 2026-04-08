"""Phase 1 Feature 5: Player reporting unit tests.

Tests cover:
- report_player stores the report in room.reports
- Stored report contains correct fields (reporter, target, reason, timestamp)
- Multiple reports accumulate without overwriting
- get_reports returns all reports to the room host
- get_reports returns empty list to non-host players
- A player can report themselves (no special restriction)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.models import Puzzle
from app.room import Room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle() -> Puzzle:
    return Puzzle(
        id="p1", title="T", surface="S", truth="X",
        key_facts=[], hints=[], difficulty="easy", tags=[],
    )


def _make_room_with_host_and_player() -> tuple[Room, str, str]:
    """Return (room, host_player_id, other_player_id)."""
    room = Room("RP0001", puzzle=_make_puzzle())
    room.add_player("host", "Host", MagicMock())
    room.add_player("other", "Other", MagicMock())
    # host_player_id is set to first joiner
    assert room.host_player_id == "host"
    return room, "host", "other"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_report_player_stores_report():
    room, host, other = _make_room_with_host_and_player()
    room.report_player(other, host, "spoiling")
    assert len(room.reports) == 1


def test_report_has_correct_fields():
    room, host, other = _make_room_with_host_and_player()
    before = time.time()
    report = room.report_player(other, host, "spoiling")
    assert report["reporter_id"] == other
    assert report["target_id"] == host
    assert report["reason"] == "spoiling"
    assert report["timestamp"] >= before


def test_multiple_reports_accumulate():
    room, host, other = _make_room_with_host_and_player()
    room.report_player(other, host, "spoiling")
    room.report_player(other, host, "harassment")
    room.report_player(host, other, "cheating")
    assert len(room.reports) == 3


def test_get_reports_returns_all_to_host():
    room, host, other = _make_room_with_host_and_player()
    room.report_player(other, host, "spoiling")
    room.report_player(host, other, "cheating")
    reports = room.get_reports(host)
    assert len(reports) == 2


def test_get_reports_returns_empty_to_non_host():
    room, host, other = _make_room_with_host_and_player()
    room.report_player(other, host, "spoiling")
    reports = room.get_reports(other)
    assert reports == []


def test_get_reports_returns_empty_to_unknown_player():
    room, _, _ = _make_room_with_host_and_player()
    reports = room.get_reports("stranger")
    assert reports == []
