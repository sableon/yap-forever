"""The player's profile (region, ruleset, faction, characters) and their auction house."""
import hashlib
import json
import math
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from yap_forever.settings import command_hint

STANDINGS = ("Neutral", "Friendly", "Honored", "Revered", "Exalted")
REGIONS = ("eu", "us", "kr", "tw")
FACTIONS = ("alliance", "horde")
OVERTIME_READINGS = ("relative", "points")
MAX_OVERTIME = 5


@dataclass
class Character:
    name: str
    favor_standing: str = "Neutral"
    working_overtime: int = 0  # Working Overtime talent rank, 0-5
    dedicated_study: bool = False  # Dedicated Study talent taken
    ruleset: int | None = None  # None = the profile's ruleset
    faction: str | None = None  # None = the profile's faction


@dataclass
class Profile:
    region: str = "eu"
    ruleset: int = 2
    faction: str = ""
    characters: dict[str, Character] = field(default_factory=dict)
    overtime_reading: str = "relative"  # how the Working Overtime bonus reads: "relative" or "points"
    study_hint_gold_per_point: float = 100  # gold a point costs on a route row before it hints at Dedicated Study
    gold: dict[tuple[int, str], float] = field(default_factory=dict)  # (ruleset, faction) -> gold shared by its characters

    def group_of(self, name: str) -> tuple[int, str]:
        """The (ruleset, faction) a character plays on: its own, or the profile's. Characters of one group
        share gold and mailable items and the auction house (region is the profile's)."""
        c = self.characters[name]
        return (c.ruleset if c.ruleset is not None else self.ruleset,
                c.faction if c.faction is not None else self.faction)


def group_label(group: tuple[int, str]) -> str:
    """'2/alliance': how profile.toml's [gold] table names a group."""
    return f"{group[0]}/{group[1]}"


_WINDOWS_REFUSED = set('<>:"/\\|?*')


def _file_part(name: str) -> str:
    """A character's name as one piece of a file name: in NFC, casefolded, whitespace runs as '-', and the
    characters Windows refuses (and control characters) dropped. Letters with accents stay."""
    dashed = re.sub(r"\s+", "-", unicodedata.normalize("NFC", name).strip().casefold())
    return "".join(c for c in dashed if c not in _WINDOWS_REFUSED and unicodedata.category(c) != "Cc")


def report_name(name: str, names: Iterable[str] = ()) -> str:
    """The part of a report file name that belongs to one character.

    names: every character name in the profile. When nothing is left of the name, or another name
    gives the same part, the first 8 hex digits of the SHA-1 of the full name are appended, so no two
    characters share report files."""
    part = _file_part(name)
    clash = any(other != name and _file_part(other) == part for other in names)
    if not part or clash:
        part += "-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return part


def _check(key: str, value, allowed) -> None:
    if value not in allowed:
        raise ValueError(f"{key} = {value!r} in profile.toml: use one of {', '.join(map(str, allowed))}")


def _overtime(key: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_OVERTIME:
        raise ValueError(f"{key} = {value!r} in profile.toml: use a whole number 0-{MAX_OVERTIME}")
    return value


def _flag(key: str, value) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{key} = {value!r} in profile.toml: use true or false")
    return value


def _positive(key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} = {value!r} in profile.toml: use a number of gold above 0")
    return value


def _ruleset(key: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} = {value!r} in profile.toml: use a ruleset number such as 2")
    return value


def _gold_table(table) -> dict[tuple[int, str], float]:
    if not isinstance(table, dict):
        raise ValueError(f'gold = {table!r} in profile.toml: use a [gold] table, e.g. "2/alliance" = 45')
    out = {}
    for key, value in table.items():
        match = re.fullmatch(r"(\d+)/(\w+)", str(key))
        if not match or int(match.group(1)) < 1 or match.group(2) not in FACTIONS:
            raise ValueError(f'gold.{key} in profile.toml: name the group as "<ruleset>/<faction>", '
                             f'e.g. "2/alliance" (factions: {", ".join(FACTIONS)})')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"gold.{key} = {value!r} in profile.toml: use a number of gold, 0 or more")
        out[(int(match.group(1)), match.group(2))] = value
    return out


def load_profile(path: Path) -> Profile:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'no {path.name} yet: run "{command_hint("init")}" first')
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    region = d.get("region", "eu")
    faction = d.get("faction", "")
    _check("region", region, REGIONS)
    _check("faction", faction, FACTIONS)
    reading = d.get("working_overtime_reading", "relative")
    _check("working_overtime_reading", reading, OVERTIME_READINGS)
    hint = _positive("study_hint_gold_per_point", d.get("study_hint_gold_per_point", 100))
    chars = {}
    for name, c in d.get("characters", {}).items():
        standing = c.get("favor_standing", "Neutral")
        _check(f"characters.{name}.favor_standing", standing, STANDINGS)
        overtime = _overtime(f"characters.{name}.working_overtime", c.get("working_overtime", 0))
        study = _flag(f"characters.{name}.dedicated_study", c.get("dedicated_study", False))
        own_ruleset = _ruleset(f"characters.{name}.ruleset", c["ruleset"]) if "ruleset" in c else None
        own_faction = c.get("faction")
        if "faction" in c:
            _check(f"characters.{name}.faction", own_faction, FACTIONS)
        chars[name] = Character(name, standing, overtime, study, own_ruleset, own_faction)
    return Profile(region, int(d.get("ruleset", 2)), faction, chars, reading, hint,
                   _gold_table(d["gold"]) if "gold" in d else {})


def save_house(path: Path, house: int, region: str, ruleset: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "house": house, "region": region, "ruleset": ruleset,
        "found": datetime.now(timezone.utc).isoformat(timespec="seconds")}), encoding="utf-8")


def load_house(path: Path) -> int:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f'no auction house yet: post a marker listing in game, then run "{command_hint("probe --item ID --buyout COPPER")}"')
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["house"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f'{path} is damaged ({type(e).__name__}): post a marker listing in game, then run '
                         f'"{command_hint("probe --item ID --buyout COPPER")}"') from None
