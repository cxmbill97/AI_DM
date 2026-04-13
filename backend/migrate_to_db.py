"""One-time migration: load all JSON puzzle/script files into content.db.

Run from the backend/ directory:
    uv run python migrate_to_db.py

Safe to re-run — uses INSERT OR REPLACE so existing rows are updated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the app package is importable from this script's location
sys.path.insert(0, str(Path(__file__).parent))

from app.models import Puzzle, Script
import app.content_db as db

PUZZLES_DIR = Path(__file__).parent / "data" / "puzzles"
SCRIPTS_DIR = Path(__file__).parent / "data" / "scripts"


def migrate_puzzles() -> int:
    count = 0
    for lang_dir in sorted(PUZZLES_DIR.iterdir()):
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        for path in sorted(lang_dir.glob("*.json")):
            try:
                puzzle = Puzzle.model_validate(json.loads(path.read_text("utf-8")))
                db.upsert_puzzle(puzzle, lang)
                print(f"  puzzle  [{lang}] {puzzle.id}")
                count += 1
            except Exception as exc:
                print(f"  ERROR   [{lang}] {path.name}: {exc}", file=sys.stderr)
    return count


def migrate_scripts() -> int:
    count = 0
    for lang_dir in sorted(SCRIPTS_DIR.iterdir()):
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        for path in sorted(lang_dir.glob("*.json")):
            try:
                script = Script.model_validate(json.loads(path.read_text("utf-8")))
                db.upsert_script(script, lang)
                print(f"  script  [{lang}] {script.id}")
                count += 1
            except Exception as exc:
                print(f"  ERROR   [{lang}] {path.name}: {exc}", file=sys.stderr)
    return count


if __name__ == "__main__":
    print("Migrating puzzles …")
    n_puzzles = migrate_puzzles()

    print("\nMigrating scripts …")
    n_scripts = migrate_scripts()

    print(f"\nDone — {n_puzzles} puzzles, {n_scripts} scripts loaded into content.db")
