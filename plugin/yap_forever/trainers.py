"""Profession trainers and the services near them, from Questie's Forever NPC and object DBs.

A trainer is an NPC with the trainer flag whose title (subName) names one of the six crafting
professions. The title carries the rank the NPC trains ("Master Blacksmith" is the trainer for
the skill 225-300 step; see RANK_BY_CAP). Specialisation masters ("Master Dragonscale
Leatherworker") and NPCs with no spawn (placeholders such as "World Alchemy Trainer") are left out.
Coordinates are map percentages (0-100) inside a zone; (-1, -1) means "inside an instance".
"""
import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from yap_forever import settings
from yap_forever.lualit import extract_table, parse

RANKS = ("Journeyman", "Expert", "Artisan", "Master")
RANK_BY_CAP = {75: "Journeyman", 150: "Expert", 225: "Artisan", 300: "Master"}

TRAINER_FLAG, BANKER_FLAG, AUCTIONEER_FLAG = 0x10, 0x100, 0x1000  # mangos-classic npcFlags

# Within about 5 map units (a few hundred yards in a typical zone) is a short walk from the trainer:
# Booty Bay's and Gadgetzan's bank, auction house and mailbox all sit within 3 of their masters,
# while a capital's bank is 10 or more away from its trainers.
NEARBY_RADIUS = 5.0

# AreaTable IDs of each faction's capital cities, where any Expert or Journeyman trainer will do
# (the Exodar and Silvermoon only exist in later data).
CAPITALS = {"alliance": (1519, 1537, 1657, 3557), "horde": (1637, 1638, 1497, 3487)}

_PROFESSION_BY_WORD = {
    "Alchemist": 171, "Alchemy": 171,
    "Blacksmith": 164, "Blacksmithing": 164,
    "Enchanter": 333, "Enchanting": 333,
    "Engineer": 202, "Engineering": 202,
    "Leatherworker": 165, "Leatherworking": 165, "Leathercrafter": 165,
    "Tailor": 197, "Tailoring": 197,
}
_PEOPLE = {"Alchemist", "Blacksmith", "Enchanter", "Engineer", "Leatherworker", "Tailor"}
_TITLE = re.compile(rf"(?:({'|'.join(RANKS)}) )?({'|'.join(_PROFESSION_BY_WORD)})( Trainer)?")

# Fields of an NPC row in foreverNpcDB.lua
_NAME, _SPAWNS, _ZONE, _FRIENDLY, _TITLE_AT, _FLAGS = 0, 6, 8, 12, 13, 14


@dataclass(frozen=True)
class Trainer:
    npc_id: int
    name: str
    profession: int  # skill line
    rank: str  # RANKS, or "" when the title names no rank
    sides: str  # "A", "H" or "AH"
    zone: int
    coords: tuple[float, float] | None  # None for an instance (the data says (-1, -1))
    title_confirmed: bool  # False for odd titles: no rank, or not the usual "<Rank> <Profession>"
    title: str = ""


@dataclass(frozen=True)
class Services:
    bank: bool
    auction: bool
    mail: bool
    # The auction house within reach is friendly to both factions (Booty Bay, Gadgetzan, Everlook):
    # it has its own prices and a higher deposit than the faction one the planner prices with.
    neutral_auction: bool = False


@dataclass(frozen=True)
class Closest:
    """The service nearest to a trainer in the same zone, when none is within a short walk."""
    kind: str  # "mailbox", "bank" or "auction"
    neutral: bool = False  # for an auction house: friendly to both factions


@dataclass
class TrainerData:
    trainers: list[Trainer]
    npc_rows: dict[int, list]
    mailboxes: list[tuple[int, float, float]]
    zones: dict[int, str]
    parents: dict[int, int] = field(default_factory=dict)  # AreaTable ParentAreaID (0: none)

    def zone_name(self, zone: int) -> str:
        return zone_name(zone, self.zones)

    def parent_zone(self, zone: int) -> int | None:
        """The zone an instance or sub-area lies in, when the data gives one that is itself a zone.
        A parent that is itself a sub-area is dropped on purpose: it would name a place players don't use."""
        parent = self.parents.get(zone, 0)
        return parent if parent in self.zones and not self.parents.get(parent, 0) else None


def rank_for_cap(cap: int) -> str:
    """The trainer title for a rank cap: 75 Journeyman, 150 Expert, 225 Artisan, 300 Master."""
    try:
        return RANK_BY_CAP[cap]
    except KeyError:
        raise ValueError(f"no trainer rank for skill cap {cap}") from None


def _damaged(what: str, why: object) -> ValueError:
    return ValueError(f"{what} is damaged ({type(why).__name__}): delete it and run the plan again "
                      f"to download it fresh")


def _table(text: str, name: str, what: str) -> dict:
    try:
        rows = parse(extract_table(text, name))
    except (KeyError, ValueError, IndexError) as e:
        raise _damaged(what, e) from None
    if not isinstance(rows, dict):
        raise _damaged(what, TypeError())
    return rows


def parse_npc_rows(npc_lua: str) -> dict[int, list]:
    """The rows of foreverNpcDB.lua by NPC id (rows too short to hold the fields are dropped)."""
    rows = _table(npc_lua, "npcData", "foreverNpcDB.lua")
    return {k: r for k, r in rows.items() if isinstance(k, int) and isinstance(r, list) and len(r) > _FLAGS}


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _flags(row: list) -> int:
    """The NPC flags of a row; 0 when the field is empty or not a number."""
    f = row[_FLAGS]
    return f if isinstance(f, int) and not isinstance(f, bool) else 0


def _spawn_points(spawns, zone: int | None = None):
    """(zone, x, y) for each placed spawn; unplaced ones (-1, -1) and malformed ones are skipped."""
    if not isinstance(spawns, dict):
        return
    for z, points in spawns.items():
        if zone is not None and z != zone:
            continue
        for p in points if isinstance(points, list) else []:
            if isinstance(p, list) and len(p) >= 2 and _number(p[0]) and _number(p[1]) and p[0] >= 0 and p[1] >= 0:
                yield z, p[0], p[1]


def _well_formed(spawns) -> bool:
    """True when spawns is {zone: [[x, y, ...], ...]} with numeric points ((-1, -1) is a number too)."""
    return (isinstance(spawns, dict) and bool(spawns) and all(
        isinstance(z, int) and isinstance(points, list)
        and all(isinstance(p, list) and len(p) >= 2 and _number(p[0]) and _number(p[1]) for p in points)
        for z, points in spawns.items()))


def _classify(title: object) -> tuple[int, str, bool] | None:
    """(profession, rank, confirmed) for a crafting trainer's title, else None."""
    m = _TITLE.fullmatch(title) if isinstance(title, str) else None
    if not m:
        return None
    rank, word, suffix = m.groups()
    return _PROFESSION_BY_WORD[word], rank or "", bool(rank) and not suffix and word in _PEOPLE


def load_trainers(npc_lua: str | dict) -> list[Trainer]:
    """Crafting trainers from the NPC DB text (or rows already parsed by parse_npc_rows)."""
    rows = parse_npc_rows(npc_lua) if isinstance(npc_lua, str) else npc_lua
    out = []
    for npc_id, r in sorted(rows.items()):
        if not _flags(r) & TRAINER_FLAG:
            continue
        found = _classify(r[_TITLE_AT])
        spawns, sides, zone = r[_SPAWNS], r[_FRIENDLY] or "AH", r[_ZONE]
        if found is None or not _well_formed(spawns) or not isinstance(r[_NAME], str):
            continue
        if not isinstance(sides, str) or (zone is not None and not isinstance(zone, int)):
            continue
        zone = zone if zone in spawns else next(iter(spawns))
        first = next(_spawn_points(spawns, zone), None)  # None: only (-1, -1), i.e. an instance
        profession, rank, confirmed = found
        out.append(Trainer(npc_id, r[_NAME], profession, rank, sides, zone,
                           first[1:] if first else None, confirmed, r[_TITLE_AT]))
    return out


def trainers_for(trainers: list[Trainer], profession: int, rank: str, faction: str) -> list[Trainer]:
    """Trainers a character of `faction` ("alliance" or "horde") can use for `rank` of `profession`.

    Trainers whose title names no rank come last: they are known by profession only.
    """
    if faction not in ("alliance", "horde"):
        raise ValueError(f"faction must be 'alliance' or 'horde', not {faction!r}")
    if rank not in RANKS:
        raise ValueError(f"rank must be one of {', '.join(RANKS)}, not {rank!r}")
    side = "A" if faction == "alliance" else "H"
    chosen = [t for t in trainers
              if t.profession == profession and t.rank in (rank, "") and side in t.sides]
    return sorted(chosen, key=lambda t: (t.rank == "", not t.title_confirmed, t.npc_id))


def load_mailboxes(object_lua: str) -> list[tuple[int, float, float]]:
    """(zone, x, y) of every placed Mailbox in the object DB text."""
    rows = _table(object_lua, "objectData", "foreverObjectDB.lua")
    return [p for r in rows.values() if isinstance(r, list) and len(r) > 3 and r[0] == "Mailbox"
            for p in _spawn_points(r[3])]


def _neutral(row: list) -> bool:
    """An auctioneer friendly to both factions (a missing field reads as both, as in load_trainers)."""
    sides = row[_FRIENDLY] or "AH"
    return isinstance(sides, str) and "A" in sides and "H" in sides


def nearby(trainer: Trainer, npc_lua_rows: dict[int, list], mailboxes: list[tuple[int, float, float]],
           radius: float) -> Services:
    """A bank, an auction house and a mailbox within `radius` map units of the trainer, same zone.

    A trainer inside an instance has no coordinates, so nothing is near it. The auction house is
    neutral when every auctioneer within the radius is friendly to both factions.
    """
    if trainer.coords is None:
        return Services(False, False, False)
    x, y = trainer.coords

    def close(points) -> bool:
        return any((px - x) ** 2 + (py - y) ** 2 <= radius ** 2 for _, px, py in points)

    def npcs(flag: int) -> list[list]:
        return [r for r in npc_lua_rows.values() if _flags(r) & flag and close(_spawn_points(r[_SPAWNS], trainer.zone))]

    auctioneers = npcs(AUCTIONEER_FLAG)
    return Services(bank=bool(npcs(BANKER_FLAG)), auction=bool(auctioneers),
                    mail=close(m for m in mailboxes if m[0] == trainer.zone),
                    neutral_auction=bool(auctioneers) and all(_neutral(r) for r in auctioneers))


def closest_service(trainer: Trainer, npc_lua_rows: dict[int, list],
                    mailboxes: list[tuple[int, float, float]]) -> Closest | None:
    """The bank, auction house or mailbox nearest to the trainer in the same zone, however far;
    None when the zone has none (or the trainer has no coordinates). A tie goes to the mailbox,
    then the bank."""
    if trainer.coords is None:
        return None
    x, y = trainer.coords

    def dist(points) -> float:
        return min(((px - x) ** 2 + (py - y) ** 2 for _, px, py in points), default=float("inf"))

    found = [(dist(m for m in mailboxes if m[0] == trainer.zone), 0, Closest("mailbox"))]
    for order, kind, flag in ((1, "bank", BANKER_FLAG), (2, "auction", AUCTIONEER_FLAG)):
        for r in npc_lua_rows.values():
            if _flags(r) & flag:
                found.append((dist(_spawn_points(r[_SPAWNS], trainer.zone)), order,
                              Closest(kind, _neutral(r) if kind == "auction" else False)))
    d, _order, best = min(found, key=lambda f: (f[0], f[1]))
    return best if d != float("inf") else None


def load_areas(path: Path) -> tuple[dict[int, str], dict[int, int]]:
    """(names, parents) by AreaTable ID (Questie's zone IDs are AreaTable IDs)."""
    names, parents = {}, {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            names[int(r["ID"])] = r["AreaName_lang"] or r["ZoneName"]
            parents[int(r["ID"])] = int(r.get("ParentAreaID") or 0)
    return names, parents


def load_zone_names(path: Path) -> dict[int, str]:
    return load_areas(path)[0]


@lru_cache(maxsize=4)
def _cached_zone_names(path: Path) -> dict[int, str]:
    return load_zone_names(path)


def zone_name(zone: int, names: Mapping[int, str] | None = None) -> str:
    """The area's name; without `names`, from AreaTable.csv in the player's game data cache."""
    if names is None:
        try:
            names = _cached_zone_names(settings.paths().gamedata / "AreaTable.csv")
        except OSError:
            names = {}
    return names.get(zone) or f"zone {zone}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise _damaged(path.name, e) from None


def load_trainer_data(d: Path | None = None) -> TrainerData:
    """Read the NPC DB, object DB and AreaTable from the game data folder."""
    d = Path(d) if d is not None else settings.paths().gamedata
    try:  # a row of the wrong shape that got past the checks: say the file is damaged, no traceback
        rows = parse_npc_rows(_read(d / "foreverNpcDB.lua"))
        found = load_trainers(rows)
    except (TypeError, KeyError, IndexError) as e:
        raise _damaged("foreverNpcDB.lua", e) from None
    try:
        boxes = load_mailboxes(_read(d / "foreverObjectDB.lua"))
    except (TypeError, KeyError, IndexError) as e:
        raise _damaged("foreverObjectDB.lua", e) from None
    try:
        zones, parents = load_areas(d / "AreaTable.csv")
    except (KeyError, ValueError) as e:  # includes a UnicodeDecodeError
        raise _damaged("AreaTable.csv", e) from None
    return TrainerData(found, rows, boxes, zones, parents)
