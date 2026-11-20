"""Plans learned from a quest instead of a trainer or a plans item."""
import tomllib
from dataclasses import dataclass
from pathlib import Path

from yap_forever.config import STATIC_DIR


@dataclass
class QuestPlan:
    name: str
    items: dict[int, int]  # handed in to the quest giver
    level: int  # character level the quest needs
    giver: str


def load_quest_plans(path: Path = STATIC_DIR / "quest_plans.toml") -> dict[int, QuestPlan]:
    with open(path, "rb") as f:
        d = tomllib.load(f)
    return {int(spell): QuestPlan(q["name"], {int(i): int(n) for i, n in q["items"].items()},
                                  int(q["level"]), q["giver"])
            for spell, q in d.items()}
