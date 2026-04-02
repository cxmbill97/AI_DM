"""Unit tests for the DM Intervention Engine.

Tests cover:
- Silence timer reset on player message
- Exponential backoff thresholds
- Silence level escalation
- Cooldown enforcement
- Explicit trigger detection (@DM, help keywords)
- record_dm_spoke increments nudge count
- Background tick returns None before threshold
- Room tick task lifecycle (start / cancel)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.intervention import InterventionEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine() -> tuple[InterventionEngine, MagicMock]:
    """Return (engine, mock_room) with minimal room stub."""
    room = MagicMock()
    room.players = {}
    room.game_session = MagicMock()
    room.game_session.finished = False
    engine = InterventionEngine(room)
    return engine, room


# ---------------------------------------------------------------------------
# Silence timer
# ---------------------------------------------------------------------------


class TestSilenceTimer:
    def test_on_player_message_resets_silence_start(self):
        engine, _ = make_engine()
        engine.silence_start = time.time() - 100  # pretend it was 100s ago
        engine.on_player_message("pid", "hello")
        assert time.time() - engine.silence_start < 1.0

    def test_on_player_message_resets_nudge_count(self):
        engine, _ = make_engine()
        engine.silence_nudge_count = 3
        engine.on_player_message("pid", "hello")
        assert engine.silence_nudge_count == 0

    def test_on_tick_returns_none_before_threshold(self):
        engine, _ = make_engine()
        engine.silence_start = time.time()  # just now
        assert engine.on_tick() is None

    def test_on_tick_returns_trigger_after_threshold(self):
        engine, _ = make_engine()
        engine.silence_start = time.time() - 50  # 50s ago (> 45s threshold)
        engine.last_dm_time = 0.0  # cooldown satisfied
        trigger = engine.on_tick()
        assert trigger is not None
        assert trigger.type == "silence"

    def test_on_tick_respects_cooldown(self):
        engine, _ = make_engine()
        engine.silence_start = time.time() - 50
        engine.last_dm_time = time.time()  # just spoke — cooldown NOT satisfied
        assert engine.on_tick() is None


# ---------------------------------------------------------------------------
# Silence thresholds and levels
# ---------------------------------------------------------------------------


class TestSilenceThresholdsAndLevels:
    def test_initial_threshold_is_45(self):
        engine, _ = make_engine()
        assert engine.silence_threshold() == pytest.approx(45.0)

    def test_threshold_doubles_each_nudge(self):
        engine, _ = make_engine()
        engine.silence_nudge_count = 1
        assert engine.silence_threshold() == pytest.approx(90.0)
        engine.silence_nudge_count = 2
        assert engine.silence_threshold() == pytest.approx(180.0)

    def test_threshold_capped_at_240(self):
        engine, _ = make_engine()
        engine.silence_nudge_count = 10  # would be 45 * 1024 without cap
        assert engine.silence_threshold() == pytest.approx(240.0)

    def test_silence_level_gentle_under_90(self):
        engine, _ = make_engine()
        assert engine.silence_level(50) == "gentle"
        assert engine.silence_level(89) == "gentle"

    def test_silence_level_nudge_90_to_180(self):
        engine, _ = make_engine()
        assert engine.silence_level(90) == "nudge"
        assert engine.silence_level(179) == "nudge"

    def test_silence_level_hint_above_180(self):
        engine, _ = make_engine()
        assert engine.silence_level(180) == "hint"
        assert engine.silence_level(300) == "hint"

    def test_on_tick_level_matches_elapsed(self):
        engine, _ = make_engine()
        engine.silence_start = time.time() - 100  # 100s → nudge
        engine.last_dm_time = 0.0
        trigger = engine.on_tick()
        assert trigger is not None
        assert trigger.level == "nudge"


# ---------------------------------------------------------------------------
# Explicit trigger detection
# ---------------------------------------------------------------------------


class TestExplicitTrigger:
    def test_at_dm_triggers(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "@DM 给个提示")
        assert trigger is not None
        assert trigger.type == "explicit"

    def test_at_dm_case_insensitive(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "@dm 你好")
        assert trigger is not None

    def test_bang_ti_shi_triggers(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "给我个提示吧")
        assert trigger is not None
        assert trigger.type == "explicit"

    def test_bang_wo_triggers(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "帮我想想")
        assert trigger is not None

    def test_gao_su_wo_triggers(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "告诉我答案")
        assert trigger is not None

    def test_normal_question_no_trigger(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("p1", "死者是被人杀死的吗？")
        assert trigger is None

    def test_explicit_trigger_player_id_set(self):
        engine, _ = make_engine()
        trigger = engine.on_player_message("player-42", "@dm 帮帮我")
        assert trigger is not None
        assert trigger.player_id == "player-42"


# ---------------------------------------------------------------------------
# record_dm_spoke
# ---------------------------------------------------------------------------


class TestRecordDmSpoke:
    def test_updates_last_dm_time(self):
        engine, _ = make_engine()
        engine.last_dm_time = 0.0
        engine.record_dm_spoke()
        assert time.time() - engine.last_dm_time < 1.0

    def test_increments_nudge_count(self):
        engine, _ = make_engine()
        engine.silence_nudge_count = 0
        engine.record_dm_spoke()
        assert engine.silence_nudge_count == 1

    def test_nudge_count_capped_at_4(self):
        engine, _ = make_engine()
        engine.silence_nudge_count = 4
        engine.record_dm_spoke()
        assert engine.silence_nudge_count == 4  # stays at 4

    def test_cooldown_not_satisfied_after_speaking(self):
        engine, _ = make_engine()
        engine.record_dm_spoke()
        assert not engine.cooldown_ok()

    def test_cooldown_satisfied_after_global_cooldown(self):
        engine, _ = make_engine()
        engine.last_dm_time = time.time() - 20  # 20s > 15s global_cooldown
        assert engine.cooldown_ok()


# ---------------------------------------------------------------------------
# Gentle message
# ---------------------------------------------------------------------------


class TestGentleMessage:
    def test_returns_non_empty_string(self):
        engine, _ = make_engine()
        msg = engine.random_gentle_message()
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_returns_chinese_text(self):
        engine, _ = make_engine()
        msg = engine.random_gentle_message()
        # At least one CJK character
        assert any("\u4e00" <= ch <= "\u9fff" for ch in msg)


# ---------------------------------------------------------------------------
# Combined scenario tests (matching task spec)
# ---------------------------------------------------------------------------


class TestCombinedScenarios:
    def test_silence_30s_no_trigger_50s_has_trigger(self):
        """Spec: call on_tick at 30s → None; at 50s → gentle trigger."""
        engine, _ = make_engine()
        engine.last_dm_time = 0.0  # cooldown always satisfied

        # Simulate 30s of silence — below 45s threshold
        engine.silence_start = time.time() - 30
        assert engine.on_tick() is None, "30s should be below threshold"

        # Simulate 50s of silence — above 45s threshold
        engine.silence_start = time.time() - 50
        trigger = engine.on_tick()
        assert trigger is not None, "50s should exceed 45s threshold"
        assert trigger.type == "silence"
        assert trigger.level == "gentle"

    def test_cooldown_blocks_then_allows(self):
        """Spec: record DM spoke → tick blocked by cooldown; set time back → allowed.

        record_dm_spoke() increments silence_nudge_count 0→1, doubling the
        threshold to 90 s.  We therefore use 100 s elapsed to stay above it.
        """
        engine, _ = make_engine()
        engine.silence_start = time.time() - 100  # 100s > 90s (post-nudge threshold)

        # DM just spoke — cooldown not satisfied regardless of silence
        engine.record_dm_spoke()
        assert engine.on_tick() is None, "cooldown should block trigger immediately after speaking"

        # Simulate global_cooldown (15s) having elapsed
        engine.last_dm_time = time.time() - 20
        trigger = engine.on_tick()
        assert trigger is not None, "trigger should fire after cooldown period"

    def test_normal_message_resets_silence_so_tick_returns_none(self):
        """Spec: 40s silence → player message → tick returns None."""
        engine, _ = make_engine()
        engine.last_dm_time = 0.0

        # Let silence build to 40s (below 45s threshold, but close)
        engine.silence_start = time.time() - 40
        # A player sends a normal message (no explicit trigger)
        engine.on_player_message("pid", "死者是被人杀的吗？")

        # Silence timer was just reset — well below any threshold
        assert engine.on_tick() is None, "silence timer should have been reset by player message"


# ---------------------------------------------------------------------------
# Room integration: engine attached to Room
# ---------------------------------------------------------------------------


class TestRoomIntegration:
    def test_room_has_intervention_engine(self):
        from app.puzzle_loader import load_puzzle
        from app.room import Room

        puzzle = load_puzzle("icicle_murder")
        room = Room("TEST01", puzzle)
        assert isinstance(room.intervention, InterventionEngine)

    def test_room_tick_task_initially_none(self):
        from app.puzzle_loader import load_puzzle
        from app.room import Room

        puzzle = load_puzzle("icicle_murder")
        room = Room("TEST02", puzzle)
        assert room._tick_task is None
