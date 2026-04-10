"""Phase 4 economy tests: coins, shop, gacha, pity."""
import pytest
from app.economy import EconomyManager, GachaEngine, GACHA_COST


@pytest.fixture
def eco():
    return EconomyManager()


@pytest.fixture
def gacha(eco):
    return GachaEngine(eco)


def test_earn_coins(eco):
    bal = eco.earn_coins("u1", 10)
    assert bal == 10
    bal = eco.earn_coins("u1", 5)
    assert bal == 15


def test_get_balance_default(eco):
    assert eco.get_balance("new_user") == 0


def test_purchase_item(eco):
    eco.earn_coins("u1", 500)
    result = eco.purchase("u1", "frame_gold")
    assert result == {"ok": True}
    assert "frame_gold" in eco.get_inventory("u1")
    assert eco.get_balance("u1") == 300  # 500 - 200


def test_purchase_insufficient_funds(eco):
    with pytest.raises(ValueError, match="Insufficient"):
        eco.purchase("u1", "frame_gold")


def test_purchase_already_owned(eco):
    eco.earn_coins("u1", 1000)
    eco.purchase("u1", "frame_gold")
    with pytest.raises(ValueError, match="already owned"):
        eco.purchase("u1", "frame_gold")


def test_purchase_unknown_item(eco):
    eco.earn_coins("u1", 1000)
    with pytest.raises(ValueError, match="Unknown"):
        eco.purchase("u1", "nonexistent")


def test_inventory_grows(eco):
    eco.earn_coins("u1", 1000)
    eco.purchase("u1", "badge_sleuth")
    eco.purchase("u1", "color_crimson")
    inv = eco.get_inventory("u1")
    assert "badge_sleuth" in inv
    assert "color_crimson" in inv


def test_gacha_costs_coins(eco, gacha):
    eco.earn_coins("u1", GACHA_COST)
    gacha.pull("u1")
    assert eco.get_balance("u1") == 0


def test_gacha_insufficient_funds(eco, gacha):
    eco.earn_coins("u1", GACHA_COST - 1)
    with pytest.raises(ValueError, match="Insufficient"):
        gacha.pull("u1")


def test_pity_resets_on_ssr(eco, gacha):
    eco.earn_coins("u1", GACHA_COST * 15)
    # Force pity by pulling until SSR guaranteed (10 pulls)
    for _ in range(10):
        result = gacha.pull("u1")
        if result["rarity"] == "SSR":
            assert eco.get_pity("u1") == 0
            return
    # After 10 pulls the SSR is guaranteed and pity resets
    assert eco.get_pity("u1") == 0


def test_gacha_result_has_item(eco, gacha):
    eco.earn_coins("u1", GACHA_COST)
    result = gacha.pull("u1")
    assert "item" in result
    assert "rarity" in result
    assert result["rarity"] in ("R", "SR", "SSR")
    assert "id" in result["item"]
