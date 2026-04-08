"""Pet companion system — each player has a persistent AI pet."""
from __future__ import annotations
import random
from typing import Optional

PET_MOODS = ["happy", "neutral", "sleepy", "excited"]
PET_LEVELS = {1: 0, 2: 100, 3: 300, 4: 600, 5: 1000}  # XP thresholds


class Pet:
    def __init__(self, owner_id: str, name: str = "Buddy", species: str = "fox"):
        self.owner_id = owner_id
        self.name = name
        self.species = species
        self.level = 1
        self.xp = 0
        self.mood = "neutral"
        self.personality_traits: list[str] = []  # e.g. ["curious", "loyal"]
        self.memory: list[str] = []  # short-term event log (last 10)

    def gain_xp(self, amount: int) -> dict:
        """Award XP to pet, return level-up info if applicable."""
        self.xp += amount
        leveled_up = False
        new_level = self.level
        for lvl in sorted(PET_LEVELS.keys(), reverse=True):
            if self.xp >= PET_LEVELS[lvl]:
                new_level = lvl
                break
        if new_level > self.level:
            self.level = new_level
            leveled_up = True
        self._update_mood()
        return {"xp": self.xp, "level": self.level, "leveled_up": leveled_up}

    def _update_mood(self):
        if self.xp % 100 == 0:
            self.mood = "excited"
        elif self.level >= 3:
            self.mood = "happy"
        else:
            self.mood = random.choice(PET_MOODS)

    def add_memory(self, event: str):
        self.memory.append(event)
        if len(self.memory) > 10:
            self.memory.pop(0)

    def generate_comment(self, context: str) -> str:
        """Generate a pet comment based on context and personality."""
        mood_prefixes = {
            "happy": ["Yay! ", "Great! ", "*wags tail* "],
            "excited": ["WOW! ", "OMG! ", "!!! "],
            "sleepy": ["*yawn* ", "zzz... ", "Hmm... "],
            "neutral": ["", "Hmm, ", "Well, "],
        }
        prefix = random.choice(mood_prefixes.get(self.mood, [""]))
        comments = {
            "correct": [f"{prefix}That was brilliant!", f"{prefix}You got it!", f"{prefix}Amazing deduction!"],
            "close": [f"{prefix}So close!", f"{prefix}Almost there!", f"{prefix}You're on the right track!"],
            "wrong": [f"{prefix}Keep trying!", f"{prefix}Don't give up!", f"{prefix}Think harder!"],
            "hint": [f"{prefix}Interesting hint...", f"{prefix}That changes things!", f"{prefix}Hmm, take note of that."],
        }
        choices = comments.get(context, [f"{prefix}..."])
        return random.choice(choices)

    def to_dict(self) -> dict:
        return {
            "owner_id": self.owner_id,
            "name": self.name,
            "species": self.species,
            "level": self.level,
            "xp": self.xp,
            "mood": self.mood,
            "personality_traits": self.personality_traits,
            "memory": self.memory,
        }
