"""Economy REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.economy import SHOP_ITEMS, economy_manager, gacha_engine


router = APIRouter(prefix="/economy", tags=["economy"])


def _user_id(request: Request) -> str:
    """Extract user id from JWT or fall back to IP for anonymous demo use."""
    from app.auth import decode_jwt  # noqa: PLC0415
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = decode_jwt(auth.removeprefix("Bearer ").strip())
            return str(payload["sub"])
        except ValueError:
            pass
    # Fallback: use client IP (demo / unauthenticated mode)
    return request.client.host if request.client else "anon"


@router.get("/balance")
def get_balance(user_id: str = Depends(_user_id)) -> dict:
    return {"balance": economy_manager.get_balance(user_id)}


@router.post("/pull")
def gacha_pull(user_id: str = Depends(_user_id)) -> dict:
    try:
        result = gacha_engine.pull(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return result


@router.get("/shop")
def get_shop() -> list[dict]:
    return SHOP_ITEMS


class PurchaseRequest(BaseModel):
    item_id: str


@router.post("/purchase")
def purchase_item(body: PurchaseRequest, user_id: str = Depends(_user_id)) -> dict:
    try:
        economy_manager.purchase(user_id, body.item_id)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return {"ok": True, "balance": economy_manager.get_balance(user_id)}


@router.get("/inventory")
def get_inventory(user_id: str = Depends(_user_id)) -> list[str]:
    return economy_manager.get_inventory(user_id)
