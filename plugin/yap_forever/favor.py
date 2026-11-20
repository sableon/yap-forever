"""Merchant's Favor recipes and crate turn-ins."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from yap_forever.config import STATIC_DIR
from yap_forever.profile import STANDINGS


@dataclass
class Turnin:
    name: str
    items: dict[int, int]
    favor: int


@dataclass
class FavorData:
    recipes: dict[int, int]  # recipe spell -> Favor price
    skills: dict[int, int] = field(default_factory=dict)  # recipe spell -> required skill, when known
    turnins: list[Turnin] = field(default_factory=list)
    note: str = ""  # said in the guide and the report when this is not the character's whole list


def load_favor(standing: str, path: Path | None = None) -> FavorData:
    """Recipes a character at `standing` may buy, and every crate turn-in."""
    if standing not in STANDINGS:
        raise ValueError(f"unknown Favor standing {standing!r}: use one of {', '.join(STANDINGS)}")
    rank = STANDINGS.index(standing)
    path = Path(path) if path is not None else STATIC_DIR / "favor.toml"
    with open(path, "rb") as f:
        d = tomllib.load(f)
    recipes, skills = {}, {}
    for r in d.get("recipe", []):
        if STANDINGS.index(r.get("standing", "Neutral")) > rank:
            continue
        recipes[int(r["spell_id"])] = int(r["favor"])
        if "skill" in r:
            skills[int(r["spell_id"])] = int(r["skill"])
    turnins = [Turnin(t["name"], {int(k): int(v) for k, v in t.get("items", {}).items()}, int(t["favor"]))
               for t in d.get("turnin", [])]
    return FavorData(recipes, skills, turnins)


def no_favor() -> FavorData:
    """No Favor recipes and no crate turn-ins: the list is Alliance's, and Horde's isn't in the planner yet."""
    return FavorData({}, {}, [], "Merchant's Favor recipes for Horde aren't in the planner yet.")
