"""Phase 4 — Economy System tests."""
import pytest
from app.economy import GACHA_COST, MATCH_REWARD, WIN_BONUS, Rarity, Wallet


def make_wallet(player_id: str = "p1") -> Wallet:
    return Wallet(player_id=player_id)


def test_new_wallet_starts_empty():
    w = make_wallet()
    assert w.coins == 0
    assert w.inventory == []


def test_earn_increases_coins():
    w = make_wallet()
    result = w.earn(50)
    assert result["coins"] == 50
    assert result["earned"] == 50
    assert w.coins == 50


def test_earn_match_reward_constant():
    assert MATCH_REWARD == 20


def test_earn_win_bonus():
    assert WIN_BONUS == 30


def test_spend_succeeds_when_enough():
    w = make_wallet()
    w.earn(200)
    assert w.spend(100) is True
    assert w.coins == 100


def test_spend_fails_when_insufficient():
    w = make_wallet()
    w.earn(50)
    assert w.spend(100) is False
    assert w.coins == 50  # unchanged


def test_gacha_pull_single_deducts_coins():
    w = make_wallet()
    w.earn(GACHA_COST)
    result = w.gacha_pull(1)
    assert result["success"] is True
    assert w.coins == 0
    assert len(result["results"]) == 1


def test_gacha_pull_ten():
    w = make_wallet()
    w.earn(GACHA_COST * 10)
    result = w.gacha_pull(10)
    assert result["success"] is True
    assert len(result["results"]) == 10
    assert w.coins == 0


def test_gacha_pull_insufficient_coins():
    w = make_wallet()
    result = w.gacha_pull(1)
    assert result["success"] is False
    assert result["error"] == "insufficient_coins"
    assert w.coins == 0  # unchanged


def test_gacha_result_has_rarity():
    w = make_wallet()
    w.earn(GACHA_COST * 100)
    result = w.gacha_pull(10)
    for item in result["results"]:
        assert item["rarity"] in [r.value for r in Rarity]


def test_inventory_grows_after_pull():
    w = make_wallet()
    w.earn(GACHA_COST * 3)
    w.gacha_pull(3)
    assert len(w.inventory) == 3


def test_to_dict_keys():
    w = make_wallet("user42")
    d = w.to_dict()
    assert set(d.keys()) == {"player_id", "coins", "inventory", "pull_count"}
    assert d["player_id"] == "user42"
