"""Phase 1 Feature 4: Hide puzzle source unit tests.

Tests cover:
- safe_puzzle_dict strips "source" field
- safe_puzzle_dict strips "origin", "pack", "dataset" fields
- safe_puzzle_dict preserves all non-sensitive fields
- Puzzle dict with no hidden fields passes through unchanged
- All four hidden fields stripped in one call
"""

from __future__ import annotations

import pytest

from app.puzzle_utils import safe_puzzle_dict


def test_strips_source_field():
    data = {"id": "p1", "title": "T", "source": "book2023"}
    result = safe_puzzle_dict(data)
    assert "source" not in result
    assert result["id"] == "p1"
    assert result["title"] == "T"


def test_strips_origin_field():
    data = {"id": "p1", "origin": "some_origin"}
    result = safe_puzzle_dict(data)
    assert "origin" not in result


def test_strips_pack_field():
    data = {"id": "p1", "pack": "premium_pack"}
    result = safe_puzzle_dict(data)
    assert "pack" not in result


def test_strips_dataset_field():
    data = {"id": "p1", "dataset": "dataset_v2"}
    result = safe_puzzle_dict(data)
    assert "dataset" not in result


def test_preserves_all_other_fields():
    data = {
        "id": "p1",
        "title": "My Puzzle",
        "surface": "A man dies.",
        "hints": ["h1"],
        "difficulty": "hard",
    }
    result = safe_puzzle_dict(data)
    assert result == data  # nothing stripped


def test_strips_all_four_hidden_fields_at_once():
    data = {
        "id": "p1",
        "source": "s",
        "origin": "o",
        "pack": "pk",
        "dataset": "ds",
        "title": "keep me",
    }
    result = safe_puzzle_dict(data)
    assert set(result.keys()) == {"id", "title"}
