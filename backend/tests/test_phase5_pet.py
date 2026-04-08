"""Phase 5 — Pet + AI Companion System tests."""
import pytest
from app.pet import Pet, PET_LEVELS


def make_pet(owner_id: str = "p1") -> Pet:
    return Pet(owner_id=owner_id)


def test_new_pet_defaults():
    pet = make_pet()
    assert pet.level == 1
    assert pet.xp == 0
    assert pet.mood == "neutral"
    assert pet.memory == []


def test_gain_xp_increases_xp():
    pet = make_pet()
    result = pet.gain_xp(50)
    assert result["xp"] == 50
    assert pet.xp == 50


def test_level_up_at_100_xp():
    pet = make_pet()
    result = pet.gain_xp(100)
    assert result["level"] == 2
    assert result["leveled_up"] is True


def test_no_level_up_below_threshold():
    pet = make_pet()
    result = pet.gain_xp(99)
    assert result["level"] == 1
    assert result["leveled_up"] is False


def test_mood_updates_after_xp():
    pet = make_pet()
    pet.gain_xp(10)
    # mood is one of valid moods
    assert pet.mood in ["happy", "neutral", "sleepy", "excited"]


def test_add_memory_appends():
    pet = make_pet()
    pet.add_memory("event1")
    assert "event1" in pet.memory


def test_add_memory_keeps_last_10():
    pet = make_pet()
    for i in range(15):
        pet.add_memory(f"event{i}")
    assert len(pet.memory) == 10
    assert "event14" in pet.memory
    assert "event0" not in pet.memory


def test_generate_comment_correct():
    pet = make_pet()
    comment = pet.generate_comment("correct")
    assert isinstance(comment, str)
    assert len(comment) > 0


def test_generate_comment_wrong():
    pet = make_pet()
    comment = pet.generate_comment("wrong")
    assert isinstance(comment, str)
    assert len(comment) > 0


def test_to_dict_keys():
    pet = make_pet("user7")
    d = pet.to_dict()
    expected = {"owner_id", "name", "species", "level", "xp", "mood", "personality_traits", "memory"}
    assert set(d.keys()) == expected
    assert d["owner_id"] == "user7"


def test_rename_pet():
    pet = make_pet()
    pet.name = "Spark"
    assert pet.name == "Spark"
    assert pet.to_dict()["name"] == "Spark"
