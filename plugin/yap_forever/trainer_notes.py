"""Facts from play about trainers (data_static/trainer_notes.toml): reach level, flight path, tips.

The file ships with the planner, so a mistake in it is a mistake to fix in the file: the message
names the key and what is wrong with it.
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from yap_forever.config import PROFESSION_IDS, STATIC_DIR

MAX_LEVEL = 60
_TRAINER_KEYS = {"reach_level", "flight_path", "note", "note_alliance", "note_horde", "group_level", "solo_level",
                 "nearby"}
_CITY_KEYS = {"tip", "groups"}
SERVICES = ("bank", "auction", "mail")  # what `nearby` may name
_FILE = "trainer_notes.toml"


@dataclass(frozen=True)
class TrainerNote:
    reach_level: int | None = None  # the character level from which the first trip is comfortable
    flight_path: bool = False  # a flight path makes repeat visits easy
    note: str = ""
    note_alliance: str = ""  # said after `note` to an Alliance character only
    note_horde: str = ""  # ... to a Horde character only
    group_level: int | None = None  # an instance trainer: the level to go with a group ...
    solo_level: int | None = None  # ... and to go alone
    nearby: tuple[str, ...] = ()  # services known from play to be near, whatever the radius finds (SERVICES)


@dataclass(frozen=True)
class Notes:
    trainers: dict[int, TrainerNote]  # by NPC ID
    cities: dict[int, str]  # tips by the capital's AreaTable zone ID
    # by zone ID: the skill lines whose trainers are close together, one set per group of the city
    city_groups: dict[int, tuple[frozenset[int], ...]] = field(default_factory=dict)


def _bad(why: str) -> ValueError:
    return ValueError(f"{_FILE} (shipped with the planner) is not usable: {why}")


def _id(key: object, what: str) -> int:
    if isinstance(key, str) and key.isdigit() and int(key) > 0:
        return int(key)
    raise _bad(f"{what} key {key!r} is not a positive number (an NPC ID or a zone ID)")


def _level(table: dict, key: str, where: str) -> int | None:
    if key not in table:
        return None
    v = table[key]
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_LEVEL:
        raise _bad(f"{where} {key} must be a whole number from 1 to {MAX_LEVEL}, not {v!r}")
    return v


def _trainer(npc: int, table: object) -> TrainerNote:
    where = f"trainers.{npc}"
    if not isinstance(table, dict):
        raise _bad(f"{where} must be a table")
    unknown = sorted(set(table) - _TRAINER_KEYS)
    if unknown:
        raise _bad(f"{where} has unknown key(s) {', '.join(unknown)}; known: {', '.join(sorted(_TRAINER_KEYS))}")
    reach, group, solo = (_level(table, k, where) for k in ("reach_level", "group_level", "solo_level"))
    flight = table.get("flight_path", False)
    if not isinstance(flight, bool):
        raise _bad(f"{where} flight_path must be true or false, not {flight!r}")
    sentences = []
    for key in ("note", "note_alliance", "note_horde"):
        note = table.get(key, "")
        if not isinstance(note, str) or (key in table and not note.strip()):
            raise _bad(f"{where} {key} must be a non-empty sentence, not {note!r}")
        sentences.append(note)
    nearby = table.get("nearby", [])
    if (not isinstance(nearby, list) or ("nearby" in table and not nearby)
            or not all(isinstance(n, str) and n in SERVICES for n in nearby) or len(set(nearby)) != len(nearby)):
        raise _bad(f"{where} nearby must be a list of different services from {', '.join(SERVICES)}, not {nearby!r}")
    if (group is None) != (solo is None):
        raise _bad(f"{where} needs group_level and solo_level together")
    if group is not None and reach is not None:
        raise _bad(f"{where} has reach_level as well as group_level and solo_level: use one kind")
    if group is not None and solo < group:
        raise _bad(f"{where} solo_level ({solo}) is below group_level ({group})")
    return TrainerNote(reach, flight, *sentences, group, solo, tuple(nearby))


def _groups(where: str, value: object) -> tuple[frozenset[int], ...]:
    """A city's groups: lists of profession names, each name once in all, trainers of one group close together."""
    names = ", ".join(PROFESSION_IDS)
    if not isinstance(value, list) or not value:
        raise _bad(f"{where} must be a list of lists of profession names ({names}), not {value!r}")
    seen: set[str] = set()
    out = []
    for group in value:
        if not isinstance(group, list) or not group:
            raise _bad(f"{where} must hold non-empty lists of profession names ({names}), not {group!r}")
        for n in group:
            if not isinstance(n, str) or n not in PROFESSION_IDS:
                raise _bad(f"{where} has {n!r}, which is not a profession name ({names})")
            if n in seen:
                raise _bad(f"{where} names {n} more than once")
            seen.add(n)
        out.append(frozenset(PROFESSION_IDS[n] for n in group))
    return tuple(out)


def load_notes(path: Path | None = None) -> Notes:
    """The notes from the shipped file (or `path`); ValueError with a message when it is not usable."""
    path = Path(path) if path is not None else STATIC_DIR / _FILE
    try:
        with open(path, "rb") as f:
            d = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise _bad(f"it is not valid TOML ({e})") from None
    except UnicodeDecodeError:
        raise _bad("it is not UTF-8 text") from None
    except OSError as e:
        raise ValueError(f"{_FILE} could not be read ({e.strerror or e})") from None
    unknown = sorted(set(d) - {"trainers", "cities"})
    if unknown:
        raise _bad(f"unknown table(s) {', '.join(unknown)}; known: trainers, cities")
    trainers = d.get("trainers", {})
    cities = d.get("cities", {})
    if not isinstance(trainers, dict):
        raise _bad("trainers must be a table of [trainers.<NPC ID>] tables")
    if not isinstance(cities, dict):
        raise _bad("cities must be a table of <zone ID> = \"tip\" lines")
    out_t = {_id(k, "trainers"): _trainer(_id(k, "trainers"), v) for k, v in trainers.items()}
    out_c, out_g = {}, {}
    for k, v in cities.items():
        zone, where = _id(k, "cities"), f"cities.{k}"
        table = v if isinstance(v, dict) else {"tip": v}
        unknown = sorted(set(table) - _CITY_KEYS)
        if unknown:
            raise _bad(f"{where} has unknown key(s) {', '.join(unknown)}; known: {', '.join(sorted(_CITY_KEYS))}")
        if "tip" not in table and "groups" not in table:
            raise _bad(f"{where} must be a non-empty sentence (or a table with a tip or groups)")
        if "tip" in table:
            tip = table["tip"]
            if not isinstance(tip, str) or not tip.strip():
                raise _bad(f"{where} must be a non-empty sentence (or a table with a non-empty tip), not {tip!r}")
            out_c[zone] = tip
        if "groups" in table:
            out_g[zone] = _groups(f"{where} groups", table["groups"])
    return Notes(out_t, out_c, out_g)
