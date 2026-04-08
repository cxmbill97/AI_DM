"""Economy router — coins, gacha, and cosmetics endpoints."""
from fastapi import APIRouter, HTTPException

from ..economy import GACHA_COST, MATCH_REWARD, WIN_BONUS, Wallet

router = APIRouter(prefix="/economy", tags=["economy"])

# In-memory store (replace with DB in production)
_wallets: dict[str, Wallet] = {}


def _get_or_create(player_id: str) -> Wallet:
    if player_id not in _wallets:
        _wallets[player_id] = Wallet(player_id=player_id)
    return _wallets[player_id]


@router.get("/{player_id}")
def get_wallet(player_id: str):
    return _get_or_create(player_id).to_dict()


@router.post("/{player_id}/earn_match")
def earn_match_reward(player_id: str, won: bool = False):
    wallet = _get_or_create(player_id)
    amount = MATCH_REWARD + (WIN_BONUS if won else 0)
    result = wallet.earn(amount, reason="win" if won else "match")
    return result


@router.post("/{player_id}/gacha")
def gacha_pull(player_id: str, count: int = 1):
    if count < 1 or count > 10:
        raise HTTPException(status_code=400, detail="count must be 1–10")
    wallet = _get_or_create(player_id)
    result = wallet.gacha_pull(count)
    if not result["success"]:
        raise HTTPException(status_code=402, detail=result.get("error", "payment_required"))
    return result


@router.get("/{player_id}/inventory")
def get_inventory(player_id: str):
    wallet = _get_or_create(player_id)
    return {"player_id": player_id, "inventory": wallet.inventory, "coins": wallet.coins}


@router.get("/info/constants")
def get_constants():
    return {
        "gacha_cost": GACHA_COST,
        "match_reward": MATCH_REWARD,
        "win_bonus": WIN_BONUS,
    }
