"""Pet router — companion pet management endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..pet import Pet

router = APIRouter(prefix="/pet", tags=["pet"])

# In-memory store (replace with DB in production)
_pets: dict[str, Pet] = {}


def _get_or_create(player_id: str) -> Pet:
    if player_id not in _pets:
        _pets[player_id] = Pet(owner_id=player_id)
    return _pets[player_id]


class RenameRequest(BaseModel):
    name: str


class CommentRequest(BaseModel):
    context: str  # "correct" | "close" | "wrong" | "hint"


@router.get("/{player_id}")
def get_pet(player_id: str):
    return _get_or_create(player_id).to_dict()


@router.post("/{player_id}/rename")
def rename_pet(player_id: str, req: RenameRequest):
    pet = _get_or_create(player_id)
    pet.name = req.name
    return pet.to_dict()


@router.post("/{player_id}/gain_xp")
def gain_xp(player_id: str, amount: int = 10):
    pet = _get_or_create(player_id)
    result = pet.gain_xp(amount)
    return {**pet.to_dict(), **result}


@router.post("/{player_id}/comment")
def get_comment(player_id: str, req: CommentRequest):
    pet = _get_or_create(player_id)
    comment = pet.generate_comment(req.context)
    pet.add_memory(f"commented on {req.context}")
    return {"comment": comment, "mood": pet.mood}
