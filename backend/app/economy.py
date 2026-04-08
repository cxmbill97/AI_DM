"""Economy system — in-game currency, gacha pulls, and cosmetics."""
from __future__ import annotations

import random
from enum import Enum
from typing import Optional


class Rarity(str, Enum):
    R = "R"
    SR = "SR"
    SSR = "SSR"


RARITY_WEIGHTS = {Rarity.R: 0.70, Rarity.SR: 0.25, Rarity.SSR: 0.05}

COSMETICS_POOL: list[dict] = [
    {"id": "avatar_fox", "name": "Fox Avatar", "rarity": Rarity.R, "type": "avatar"},
    {"id": "avatar_wolf", "name": "Wolf Avatar", "rarity": Rarity.SR, "type": "avatar"},
    {"id": "avatar_dragon", "name": "Dragon Avatar", "rarity": Rarity.SSR, "type": "avatar"},
    {"id": "frame_gold", "name": "Gold Frame", "rarity": Rarity.SR, "type": "frame"},
    {"id": "frame_basic", "name": "Basic Frame", "rarity": Rarity.R, "type": "frame"},
    {"id": "title_detective", "name": "Detective Title", "rarity": Rarity.R, "type": "title"},
    {"id": "title_mastermind", "name": "Mastermind Title", "rarity": Rarity.SSR, "type": "title"},
    {"id": "effect_sparkle", "name": "Sparkle Effect", "rarity": Rarity.SR, "type": "effect"},
]

GACHA_COST = 100  # coins per pull
MATCH_REWARD = 20  # coins earned per match played
WIN_BONUS = 30     # extra coins for winning


class Wallet:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.coins: int = 0
        self.inventory: list[dict] = []
        self.pull_history: list[dict] = []

    def earn(self, amount: int, reason: str = "match") -> dict:
        self.coins += amount
        return {"coins": self.coins, "earned": amount, "reason": reason}

    def spend(self, amount: int) -> bool:
        if self.coins < amount:
            return False
        self.coins -= amount
        return True

    def gacha_pull(self, count: int = 1) -> dict:
        total_cost = GACHA_COST * count
        if not self.spend(total_cost):
            return {"success": False, "error": "insufficient_coins", "coins": self.coins}

        results = []
        for _ in range(count):
            item = self._pull_one()
            self.inventory.append(item)
            self.pull_history.append(item)
            results.append(item)

        return {
            "success": True,
            "results": results,
            "coins": self.coins,
            "spent": total_cost,
        }

    def _pull_one(self) -> dict:
        roll = random.random()
        cumulative = 0.0
        chosen_rarity = Rarity.R
        for rarity, weight in RARITY_WEIGHTS.items():
            cumulative += weight
            if roll < cumulative:
                chosen_rarity = rarity
                break

        pool = [c for c in COSMETICS_POOL if c["rarity"] == chosen_rarity]
        if not pool:
            pool = COSMETICS_POOL
        item = random.choice(pool)
        return {**item, "obtained_at": _now()}

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "coins": self.coins,
            "inventory": self.inventory,
            "pull_count": len(self.pull_history),
        }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
