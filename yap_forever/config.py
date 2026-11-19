"""Credentials type, static data folder and the stock file."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "data_static"

# Profession names a player writes in stock.toml's [skills] table, and their skill line IDs.
PROFESSION_IDS = {"alchemy": 171, "blacksmithing": 164, "enchanting": 333, "engineering": 202,
                  "leatherworking": 165, "tailoring": 197}


@dataclass(frozen=True)
class Credentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    region: str = "eu"

    def __repr__(self):
        return f"Credentials(region={self.region!r}, client_id=***, client_secret=***)"

    __str__ = __repr__


@dataclass
class Stock:
    items: dict[int, int]
    favor: int
    cash: int  # copper, soft budget
    level: int
    mining: int
    short_farm_ore: int
    marker: tuple[int, int] | None
    target: int = 225  # skill both professions are planned to
    mining_goal: int = 0  # Mining skill you'll reach while farming; 0 = current
    quest_item_sales: int | None = None  # quest items you expect to sell on the AH; None = no limit
    skills: dict[int, int] = field(default_factory=dict)  # skill line -> current skill; absent = 1
    goals: dict[int, "Goal"] = field(default_factory=dict)  # skill line -> what to plan it to
    bag_slots: int | None = None  # free bag slots while crafting; None = mailbox trips not planned
    keep_greens: bool = False  # keep green crafts to disenchant on another character instead of selling
    reagent_slots: int = 0  # reagent bag slots; 0 = no reagent bag


MAX_SKILL = 300


@dataclass(frozen=True)
class Goal:
    """Where to plan a profession to: a skill, or one recipe (name or spell ID) to craft once."""
    skill: int | None = None
    recipe: str | None = None


def parse_goal(value: int | str) -> Goal:
    """A number 1-300 is a skill; a larger number is a recipe's spell ID; other text is a recipe name."""
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        n = int(text)
        if n > MAX_SKILL:
            return Goal(recipe=text)
        if n < 1:
            raise ValueError(f"target skill must be 1-{MAX_SKILL}, not {n}")
        return Goal(skill=n)
    if not text:
        raise ValueError("empty target: give a skill (1-300) or a recipe")
    return Goal(recipe=text)


def _profession_id(name: str) -> int:
    key = str(name).strip().lower()
    if key.isdigit() and int(key) in PROFESSION_IDS.values():
        return int(key)
    if key in PROFESSION_IDS:
        return PROFESSION_IDS[key]
    raise ValueError(f"unknown profession {name!r}: use one of {', '.join(sorted(PROFESSION_IDS))}")


def parse_prof_arg(text: str) -> tuple[int, Goal]:
    """'tailoring:225' or 'enchanting:Enchant Bracer - Minor Health' -> (skill line, goal)."""
    name, sep, target = text.partition(":")
    if not sep:
        raise ValueError(f"use NAME:TARGET, e.g. tailoring:225 (got {text!r})")
    return _profession_id(name), parse_goal(target)


def _skills(table: dict) -> dict[int, int]:
    out = {}
    for name, value in table.items():
        key = str(name).lower()
        if key.isdigit():
            out[int(key)] = int(value)
        elif key in PROFESSION_IDS:
            out[PROFESSION_IDS[key]] = int(value)
        else:
            raise ValueError(f"[skills] {name}: use one of {', '.join(sorted(PROFESSION_IDS))}")
    return out


def _slots(d: dict, key: str, default):
    n = int(d[key]) if key in d else default
    if n is not None and n < 0:
        raise ValueError(f"{key} must be 0 or more, not {n}")
    return n


def load_stock(path: Path) -> Stock:
    with open(path, "rb") as f:
        d = tomllib.load(f)
    m = d.get("marker", {})
    marker = None
    if m.get("item_id") and m.get("buyout_copper"):
        marker = (int(m["item_id"]), int(m["buyout_copper"]))
    return Stock(
        items={int(k): int(v) for k, v in d.get("items", {}).items()},
        favor=int(d.get("favor", 0)),
        cash=int(round(float(d.get("cash_gold", 0)) * 10000)),
        level=int(d.get("level", 1)),
        mining=int(d.get("mining", 0)),
        short_farm_ore=int(d.get("short_farm_ore", 200)),
        marker=marker,
        target=int(d.get("target", 225)),
        mining_goal=int(d.get("mining_goal", d.get("mining", 0))),
        quest_item_sales=int(d["quest_item_sales"]) if "quest_item_sales" in d else None,
        skills=_skills(d.get("skills", {})),
        goals={_profession_id(k): parse_goal(v) for k, v in d.get("goals", {}).items()},
        bag_slots=_slots(d, "bag_slots", None),
        keep_greens=bool(d.get("keep_greens", False)),
        reagent_slots=_slots(d, "reagent_slots", 0),
    )
