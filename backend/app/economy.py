"""Economy system — currency, shop, gacha with pity."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

EARN_PER_MATCH = 10
EARN_MVP_BONUS = 5
GACHA_COST = 100
SSR_PITY_THRESHOLD = 10

SHOP_ITEMS: list[dict] = [
    {"id": "frame_gold",    "name": "Gold Frame",      "cost": 200, "rarity": "SR",  "type": "frame"},
    {"id": "frame_dragon",  "name": "Dragon Frame",    "cost": 500, "rarity": "SSR", "type": "frame"},
    {"id": "color_crimson", "name": "Crimson Name",    "cost": 150, "rarity": "R",   "type": "color"},
    {"id": "color_void",    "name": "Void Blue Name",  "cost": 300, "rarity": "SR",  "type": "color"},
    {"id": "badge_sleuth",  "name": "Sleuth Badge",    "cost": 100, "rarity": "R",   "type": "badge"},
    {"id": "badge_legend",  "name": "Legend Badge",    "cost": 400, "rarity": "SSR", "type": "badge"},
    {"id": "frame_sakura",  "name": "Sakura Frame",    "cost": 180, "rarity": "R",   "type": "frame"},
    {"id": "badge_phantom", "name": "Phantom Badge",   "cost": 350, "rarity": "SR",  "type": "badge"},
]

_GACHA_POOL: dict[str, list[dict]] = {
    rarity: [i for i in SHOP_ITEMS if i["rarity"] == rarity]
    for rarity in ("R", "SR", "SSR")
}


@dataclass
class _UserEconomy:
    balance: int = 0
    inventory: list[str] = field(default_factory=list)
    pity: int = 0  # pulls since last SSR


class EconomyManager:
    def __init__(self) -> None:
        self._store: dict[str, _UserEconomy] = {}

    def _get(self, user_id: str) -> _UserEconomy:
        if user_id not in self._store:
            self._store[user_id] = _UserEconomy()
        return self._store[user_id]

    def earn_coins(self, user_id: str, amount: int) -> int:
        u = self._get(user_id)
        u.balance += amount
        return u.balance

    def get_balance(self, user_id: str) -> int:
        return self._get(user_id).balance

    def purchase(self, user_id: str, item_id: str) -> dict:
        item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if item is None:
            raise ValueError(f"Unknown item: {item_id}")
        u = self._get(user_id)
        if item_id in u.inventory:
            raise ValueError("Item already owned")
        if u.balance < item["cost"]:
            raise ValueError("Insufficient funds")
        u.balance -= item["cost"]
        u.inventory.append(item_id)
        return {"ok": True}

    def get_inventory(self, user_id: str) -> list[str]:
        return list(self._get(user_id).inventory)

    def get_pity(self, user_id: str) -> int:
        return self._get(user_id).pity


class GachaEngine:
    def __init__(self, economy: EconomyManager) -> None:
        self._eco = economy

    def pull(self, user_id: str) -> dict:
        u = self._eco._get(user_id)
        if u.balance < GACHA_COST:
            raise ValueError("Insufficient funds for gacha pull")
        u.balance -= GACHA_COST
        u.pity += 1

        # Determine rarity
        if u.pity >= SSR_PITY_THRESHOLD:
            rarity = "SSR"
        else:
            roll = random.random()
            if roll < 0.10:
                rarity = "SSR"
            elif roll < 0.40:
                rarity = "SR"
            else:
                rarity = "R"

        if rarity == "SSR":
            u.pity = 0

        pool = _GACHA_POOL.get(rarity, _GACHA_POOL["R"])
        item = random.choice(pool)

        # Add to inventory if not owned
        if item["id"] not in u.inventory:
            u.inventory.append(item["id"])

        return {"item": item, "rarity": rarity, "pity_count": u.pity}

    def get_pity(self, user_id: str) -> int:
        return self._eco.get_pity(user_id)


# Singletons
economy_manager = EconomyManager()
gacha_engine = GachaEngine(economy_manager)
