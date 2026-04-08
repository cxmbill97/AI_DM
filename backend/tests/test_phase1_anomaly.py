"""Phase 1 Feature 6: Anomaly detection unit tests.

Tests cover:
- Unrelated text returns no matches
- Text containing a key_fact triggers anomaly
- Matching is case-insensitive
- Multiple key_facts in one message are all returned
- Anomaly events are stored in suspicious_flags[player_id]
- Multiple events for the same player accumulate
- No puzzle → no anomaly (safe fallback)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models import Puzzle
from app.room import Room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle(key_facts: list[str] | None = None) -> Puzzle:
    return Puzzle(
        id="p1",
        title="T",
        surface="S",
        truth="X",
        key_facts=key_facts or ["船长自杀", "遭遇海难", "独自存活"],
        hints=[],
        difficulty="easy",
        tags=[],
    )


def _make_room(puzzle: Puzzle | None = None) -> Room:
    room = Room("AD0001", puzzle=puzzle or _make_puzzle())
    room.add_player("p1", "Alice", MagicMock())
    return room


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unrelated_text_returns_no_matches():
    room = _make_room()
    matched = room.check_anomaly("p1", "天气真好")
    assert matched == []


def test_text_containing_key_fact_triggers_anomaly():
    room = _make_room()
    matched = room.check_anomaly("p1", "我猜船长自杀了")
    assert "船长自杀" in matched


def test_matching_is_case_insensitive():
    room = _make_room(_make_puzzle(key_facts=["suicide by captain"]))
    matched = room.check_anomaly("p1", "I think it was SUICIDE BY CAPTAIN")
    assert "suicide by captain" in matched


def test_multiple_key_facts_matched_in_one_message():
    room = _make_room()
    text = "他遭遇海难然后船长自杀"
    matched = room.check_anomaly("p1", text)
    assert "遭遇海难" in matched
    assert "船长自杀" in matched


def test_anomaly_stored_in_suspicious_flags():
    room = _make_room()
    room.check_anomaly("p1", "我猜船长自杀了")
    assert "p1" in room.suspicious_flags
    assert len(room.suspicious_flags["p1"]) == 1
    event = room.suspicious_flags["p1"][0]
    assert "匹配字段" in event or "matched_phrases" in event


def test_multiple_anomaly_events_accumulate():
    room = _make_room()
    room.check_anomaly("p1", "船长自杀")
    room.check_anomaly("p1", "遭遇海难")
    assert len(room.suspicious_flags["p1"]) == 2


def test_no_puzzle_returns_empty():
    from app.models import Character, NPC, Phase, Script, ScriptMetadata, ScriptTheme, ScriptTruth

    script = Script(
        id="s1",
        title="MM",
        metadata=ScriptMetadata(player_count=2, duration_minutes=60, difficulty="beginner"),
        characters=[
            Character(id="c1", name="A", public_bio="x", secret_bio="y", is_culprit=False),
            Character(id="c2", name="B", public_bio="x", secret_bio="y", is_culprit=True),
        ],
        phases=[Phase(id="ph1", type="narration", next=None, allowed_actions=set())],
        clues=[],
        npcs=[],
        truth=ScriptTruth(culprit="c2", motive="m", method="m2", timeline="t"),
        theme=ScriptTheme(),
    )
    room = Room("MM01", script=script)
    matched = room.check_anomaly("p1", "any text here")
    assert matched == []
