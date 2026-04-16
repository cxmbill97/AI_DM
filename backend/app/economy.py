"""Economy system — currency, shop, gacha with pity.

State is persisted in the auth.db SQLite database (economy table) so that
player balances and pity counters survive server restarts.
"""
from __future__ import annotations

import json
import random
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

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

# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent.parent / "data" / "auth.db"
_db_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_economy_db() -> None:
    """Create the economy table if it does not exist. Call once at startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id        TEXT PRIMARY KEY,
                balance        INTEGER NOT NULL DEFAULT 0,
                inventory_json TEXT NOT NULL DEFAULT '[]',
                pity           INTEGER NOT NULL DEFAULT 0
            )
        """)


def _db_load(user_id: str) -> "_UserEconomy":
    with _db_lock, _conn() as conn:
        row = conn.execute(
            "SELECT balance, inventory_json, pity FROM economy WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return _UserEconomy()
    return _UserEconomy(
        balance=row["balance"],
        inventory=json.loads(row["inventory_json"]),
        pity=row["pity"],
    )


def _db_save(user_id: str, u: "_UserEconomy") -> None:
    with _db_lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO economy (user_id, balance, inventory_json, pity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance        = excluded.balance,
                inventory_json = excluded.inventory_json,
                pity           = excluded.pity
            """,
            (user_id, u.balance, json.dumps(u.inventory), u.pity),
        )


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class _UserEconomy:
    balance: int = 0
    inventory: list[str] = field(default_factory=list)
    pity: int = 0  # pulls since last SSR


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class EconomyManager:
    def __init__(self) -> None:
        # In-process cache to avoid a DB round-trip on every call.
        self._cache: dict[str, _UserEconomy] = {}

    def _get(self, user_id: str) -> _UserEconomy:
        if user_id not in self._cache:
            self._cache[user_id] = _db_load(user_id)
        return self._cache[user_id]

    def _save(self, user_id: str) -> None:
        _db_save(user_id, self._cache[user_id])

    def earn_coins(self, user_id: str, amount: int) -> int:
        u = self._get(user_id)
        u.balance += amount
        self._save(user_id)
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
        self._save(user_id)
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

        self._eco._save(user_id)
        return {"item": item, "rarity": rarity, "pity_count": u.pity}

    def get_pity(self, user_id: str) -> int:
        return self._eco.get_pity(user_id)


# Singletons
economy_manager = EconomyManager()
gacha_engine = GachaEngine(economy_manager)
