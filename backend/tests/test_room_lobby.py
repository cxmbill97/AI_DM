import pytest
from app.room import Room, RoomManager
from unittest.mock import MagicMock


def _make_puzzle():
    from app.models import Puzzle
    return Puzzle(id="p1", title="Test", surface="Q", truth="A", key_facts=[],
                  hints=[], clues=[], difficulty="easy", tags=[], private_clues={})


def _make_script():
    from app.models import Script, ScriptMetadata, ScriptTheme, ScriptTruth
    meta = ScriptMetadata(difficulty="easy", player_count=3, estimated_duration=60,
                          duration_minutes=60, genre="mystery", theme="")
    theme = ScriptTheme(background_color="#000", accent_color="#fff", font_style="serif")
    truth = ScriptTruth(culprit="X", motive="greed", method="poison", timeline="",
                        key_facts=[], full_story="X did it", cause_of_death="poison")
    from app.models import Phase
    opening = Phase(id="opening", type="opening", next=None, duration_seconds=60,
                    allowed_actions=[], dm_script="Welcome", available_clues=[],
                    per_player_content={}, reconstruction_questions=[])
    return Script(id="s1", title="Test Script", game_mode="coop",
                  metadata=meta, characters=[], phases=[opening], clues=[], npcs=[],
                  truth=truth, theme=theme)


def test_room_started_defaults_false():
    room = Room("R1", puzzle=_make_puzzle())
    assert room.started is False


def test_room_max_players_turtle_soup_default_4():
    room = Room("R1", puzzle=_make_puzzle())
    assert room.max_players == 4


def test_room_max_players_murder_mystery_matches_script():
    script = _make_script()  # player_count=3
    room = Room("R1", script=script)
    assert room.max_players == 3


def test_is_full_uses_max_players():
    room = Room("R1", puzzle=_make_puzzle())
    room.max_players = 2
    ws1, ws2 = MagicMock(), MagicMock()
    room.add_player("p1", "Alice", ws1)
    assert not room.is_full()
    room.add_player("p2", "Bob", ws2)
    assert room.is_full()


def test_host_player_id_set_on_first_join():
    room = Room("R1", puzzle=_make_puzzle())
    ws = MagicMock()
    room.add_player("p1", "Alice", ws)
    assert room.host_player_id == "p1"


def test_host_player_id_not_overwritten_by_second_join():
    room = Room("R1", puzzle=_make_puzzle())
    room.add_player("p1", "Alice", MagicMock())
    room.add_player("p2", "Bob", MagicMock())
    assert room.host_player_id == "p1"


def test_ready_players_empty_on_init():
    room = Room("R1", puzzle=_make_puzzle())
    assert room.ready_players == set()
