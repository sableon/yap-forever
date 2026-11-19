"""The player's profile (region, ruleset, faction, characters) and their auction house."""
import json
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


@dataclass
class Profile:
    region: str = "eu"
    ruleset: int = 2
    faction: str = ""
    characters: dict[str, Character] = field(default_factory=dict)
    overtime_reading: str = "relative"  # how the Working Overtime bonus reads: "relative" or "points"


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
    chars = {}
    for name, c in d.get("characters", {}).items():
        standing = c.get("favor_standing", "Neutral")
        _check(f"characters.{name}.favor_standing", standing, STANDINGS)
        overtime = _overtime(f"characters.{name}.working_overtime", c.get("working_overtime", 0))
        study = _flag(f"characters.{name}.dedicated_study", c.get("dedicated_study", False))
        chars[name] = Character(name, standing, overtime, study)
    return Profile(region, int(d.get("ruleset", 2)), faction, chars, reading)


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
