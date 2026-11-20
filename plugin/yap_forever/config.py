"""Credentials type, static data folder and the stock file."""
import math
import re
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
    mining: int  # Mining skill; above 0 the guide gives the miner's notes
    short_farm_ore: int
    mining_goal: int = 0  # Mining skill you'll reach while farming; 0 = current
    quest_item_sales: int | None = None  # quest items you expect to sell on the AH; None = no limit
    skills: dict[int, int] = field(default_factory=dict)  # skill line -> current skill; absent = 1
    goals: dict[int, "Goal"] = field(default_factory=dict)  # skill line -> what to plan it to
    bag_slots: int | None = None  # free bag slots while crafting; None = mailbox trips not planned
    keep_greens: bool = False  # keep green crafts to disenchant on another character instead of selling
    reagent_slots: int = 0  # reagent bag slots; 0 = no reagent bag
    skinning: int = 0  # Skinning skill; above 0 the guide says leather can be gathered
    shared: dict[str, dict[int, int]] = field(default_factory=dict)  # your group's other characters' mailable items,
    # by name (not in the file: set from the other characters' stock files, see shared.Group)
    budget: "Budget | None" = None  # [goals] budget: plan only as far as this gold reaches; None = to the targets


MAX_SKILL = 300


@dataclass(frozen=True)
class Goal:
    """Where to plan a profession to: a skill, or one recipe (name or spell ID) to craft once."""
    skill: int | None = None
    recipe: str | None = None


@dataclass(frozen=True)
class Budget:
    """A budget as a goal: plan each profession to the last stop this much gold reaches (see budget.cut).
    order: None raises two professions evenly; skill line IDs raise them one at a time, in that order."""
    gold: float
    order: tuple[int, ...] | None = None


def parse_order(names, key: str) -> tuple[int, ...] | None:
    """'even' -> None; profession names (a list, or text 'NAME,NAME') -> their skill line IDs, in order."""
    if isinstance(names, str):
        if names.strip().lower() == "even":
            return None
        names = [n for n in names.split(",") if n.strip()]
    if not isinstance(names, list) or not names:
        raise ValueError(f'{key}: use "even" or a list of professions, e.g. ["blacksmithing", "enchanting"]')
    try:
        out = tuple(_profession_id(n) for n in names)
    except ValueError as e:
        raise ValueError(f"{key}: {e}") from None
    if len(set(out)) < len(out):
        raise ValueError(f"{key}: a profession is named twice")
    return out


def parse_budget(value, key: str) -> float:
    """A budget in gold: a number, 0 or more."""
    n = _number(value, key)
    if n < 0:
        raise ValueError(f"{key} must be 0 or more, not {value}")
    return n


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
    for name, value in _table(table, "skills").items():
        key = str(name).lower()
        if key.isdigit():
            out[int(key)] = _whole(value, f"skills.{name}")
        elif key in PROFESSION_IDS:
            out[PROFESSION_IDS[key]] = _whole(value, f"skills.{name}")
        else:
            raise ValueError(f"[skills] {name}: use one of {', '.join(sorted(PROFESSION_IDS))}")
    return out


class StockError(ValueError):
    """A stock file that can't be read: `path` and what is wrong in it (`detail`)."""

    def __init__(self, path: Path, detail: str):
        super().__init__(f"{path}: {detail}")
        self.path, self.detail = path, detail


def _table(value, key: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{key} = {value!r}: use a [{key}] table")
    return value


def _whole(value, key: str) -> int:
    """A whole number from TOML (also 47.0, or a string of digits as older files have them)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bool) or not isinstance(value, (int, str)) or (
            isinstance(value, str) and not re.fullmatch(r"-?\d+", value.strip())):
        raise ValueError(f"{key} = {value!r}: use a whole number")
    return int(value)


def _number(value, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{key} = {value!r}: use a number")
    try:
        n = float(value)
    except ValueError:
        raise ValueError(f"{key} = {value!r}: use a number") from None
    if not math.isfinite(n):
        raise ValueError(f"{key} = {value!r}: use a number")
    return n


def _slots(d: dict, key: str, default):
    n = _whole(d[key], key) if key in d else default
    if n is not None and n < 0:
        raise ValueError(f"{key} must be 0 or more, not {n}")
    return n


def load_stock(path: Path) -> Stock:
    """The stock file; a mistake in it is a StockError that names the file and the key."""
    try:
        with open(path, "rb") as f:
            d = tomllib.load(f)
        return _stock(d)
    except tomllib.TOMLDecodeError as e:
        raise StockError(path, f"not valid TOML ({e})") from None
    except StockError:
        raise
    except ValueError as e:
        raise StockError(path, str(e)) from None


def _stock(d: dict) -> Stock:
    def whole(key, default):
        return _whole(d[key], key) if key in d else default

    items = {}
    for k, v in _table(d.get("items", {}), "items").items():
        if not str(k).isdigit():
            raise ValueError(f"items.{k}: use an item ID (a number) as the key")
        items[int(k)] = _whole(v, f"items.{k}")
    goals = {}
    table = dict(_table(d.get("goals", {}), "goals"))
    budget = None
    if "budget" in table:  # not professions: read first
        budget = Budget(parse_budget(table.pop("budget"), "goals.budget"))
    if "budget_order" in table:
        order = table.pop("budget_order")
        if budget is None:
            raise ValueError("goals.budget_order goes with goals.budget: set the budget too, or leave it out")
        budget = Budget(budget.gold, parse_order(order, "goals.budget_order"))
    for k, v in table.items():
        try:
            goals[_profession_id(k)] = parse_goal(v)
        except ValueError as e:
            raise ValueError(f"goals.{k}: {e}") from None
    return Stock(
        items=items,
        favor=whole("favor", 0),
        cash=round(_number(d.get("cash_gold", 0), "cash_gold") * 10000),
        level=whole("level", 1),
        mining=whole("mining", 0),
        skinning=_slots(d, "skinning", 0),
        short_farm_ore=whole("short_farm_ore", 200),
        mining_goal=_whole(d["mining_goal"], "mining_goal") if "mining_goal" in d else whole("mining", 0),
        quest_item_sales=whole("quest_item_sales", None),
        skills=_skills(d.get("skills", {})),
        goals=goals,
        bag_slots=_slots(d, "bag_slots", None),
        keep_greens=bool(d.get("keep_greens", False)),
        reagent_slots=_slots(d, "reagent_slots", 0),
        budget=budget,
    )
