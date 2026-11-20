"""Game data from pinned sources (skillup-forever, QuestieDB, wago.tools), cached per pinned version.

Loads the recipes and starter recipes of the professions asked for (any of the six crafts), with
items, tools, quest items, trainer ranks and fees, and vendor prices. The trainer NPC, object and
zone files are downloaded here too; `trainers.py` reads them.

Usage: python3 -m yap_forever.gamedata [--fetch] [--checks]
"""
import argparse
import csv
import dataclasses
import http.client
import os
import re
import shutil
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from yap_forever import __version__, settings
from yap_forever.lualit import extract_table, parse

BS, ENCH = 164, 333
PROFESSIONS = {171: "Alchemy", BS: "Blacksmithing", ENCH: "Enchanting", 202: "Engineering",
               165: "Leatherworking", 197: "Tailoring"}  # names; what loads is load_gamedata's choice

SKILLUP_SHA = "77337fa60453304ab0ae656466807037802435bc"
QUESTIE_SHA = "ae4404b01a45163d3ef05909395b29aafc437bc2"
WAGO_BUILD = "1.60.1.70862"
SOURCES = {
    **{f"{n}.lua": f"https://raw.githubusercontent.com/cjber/skillup-forever/{SKILLUP_SHA}/Data/{n}.lua"
       for n in ("Recipes", "Thresholds", "Trainer", "Vendor")},
    **{f"{n}.lua": f"https://raw.githubusercontent.com/Questie/QuestieDB/{QUESTIE_SHA}/data/Forever/{n}.lua"
       for n in ("foreverQuestDB", "foreverNpcDB", "foreverObjectDB")},
    **{f"{t}.csv": f"https://wago.tools/db2/{t}/csv?build={WAGO_BUILD}"
       for t in ("ItemSparse", "Item", "SpellTotems", "TotemCategory", "SkillLineAbility", "AreaTable")},
}
TRAINER_FILES = ("foreverNpcDB.lua", "foreverObjectDB.lua", "AreaTable.csv")  # guide extras, not planning data
# The cache folder for these pins (settings.Paths.gamedata): a pin change means a new folder, so a
# player's next plan downloads the new files by itself.
PIN_KEY = f"skillup-{SKILLUP_SHA[:12]}_questie-{QUESTIE_SHA[:12]}_wago-{WAGO_BUILD}"
_PIN_DIR = re.compile(r"skillup-[0-9a-f]{12}_questie-[0-9a-f]{12}_wago-[0-9.]+")
# What each file must hold to be game data: a CSV's header has these columns, a Lua file assigns these
# tables. The columns are the ones the loaders read without a default.
EXPECTED: dict[str, tuple[str, tuple[str, ...]]] = {
    "Recipes.lua": ("lua", ("RecipeData", "RecipeScrolls", "RecipeNames")),
    "Thresholds.lua": ("lua", ("Thresholds",)),
    "Trainer.lua": ("lua", ("TrainerFees", "TrainerRanks")),
    "Vendor.lua": ("lua", ("VendorPrices",)),
    "foreverQuestDB.lua": ("lua", ("questData",)),
    "foreverNpcDB.lua": ("lua", ("npcData",)),
    "foreverObjectDB.lua": ("lua", ("objectData",)),
    "ItemSparse.csv": ("csv", ("ID", "Display_lang", "OverallQualityID", "ItemLevel", "SellPrice", "BuyPrice")),
    "Item.csv": ("csv", ("ID", "ClassID")),
    "SpellTotems.csv": ("csv", ("SpellID", "RequiredTotemCategoryID_0", "RequiredTotemCategoryID_1")),
    "TotemCategory.csv": ("csv", ("ID", "TotemCategoryMask")),
    "SkillLineAbility.csv": ("csv", ("Spell", "SkillLine", "AcquireMethod")),
    "AreaTable.csv": ("csv", ("ID", "ZoneName", "AreaName_lang")),
}


@dataclass(frozen=True)
class Rank:
    cap: int
    fee: int
    required_skill: int
    level: int


def fill_rank_levels(ranks: dict[int, list[Rank]]) -> dict[int, list[Rank]]:
    """Ranks whose required character level is 0 get the level the other professions give the same cap.

    The pinned TrainerRanks give Tailoring's Master rank (cap 300) level 0 while every crafting
    profession has 35 there (a Master trainer needs level 35). Other professions' zeros are not a level
    and are ignored; when the others disagree, or none gives a level, the 0 stays. It also fills the
    gathering professions (and First Aid), which the planner does not plan. `ranks` is not changed.
    """
    levels: dict[int, set[int]] = {}
    for rs in ranks.values():
        for r in rs:
            if r.level:
                levels.setdefault(r.cap, set()).add(r.level)
    return {prof: [dataclasses.replace(r, level=next(iter(levels[r.cap])))
                   if not r.level and len(levels.get(r.cap, ())) == 1 else r for r in rs]
            for prof, rs in ranks.items()}


NO_DISENCHANT_FLAG = 0x8000  # ItemSparse Flags_0: item cannot be disenchanted
MAILABLE_BONDING = (0, 2, 3)  # ItemSparse Bonding: none, on equip, on use; 1 (on pickup) and 4 (quest) stay put

@dataclass
class ItemInfo:
    id: int
    name: str
    quality: int
    item_level: int
    class_id: int
    sell_price: int
    buy_price: int
    no_disenchant: bool = False  # client flag; e.g. Enchanting's own wands
    stack: int = 1  # most of one item a bag slot holds
    bonding: int | None = None  # ItemSparse Bonding; None = unknown (no such column, or an empty cell)

    @property
    def mailable(self) -> bool:
        """Another of your characters can be mailed one: not bound on pickup, not a quest item."""
        return self.bonding in MAILABLE_BONDING


@dataclass
class Recipe:
    spell_id: int
    name: str
    skill_line: int
    reagents: dict[int, int]
    output: tuple[int, float] | None
    thresholds: tuple[int, int, int, int]
    required_skill: int
    source: str  # trainer | starter | scroll | favor | unknown
    fee: int = 0
    scroll_item: int | None = None
    tools: list[int] = field(default_factory=list)
    inferred_skill: int | None = None  # Classic skill a trainer may ask for this recipe (TrainerInferred)
    listed_skill: int | None = None  # the Forever data's requirement, kept when safe_requirements raised it


@dataclass
class GameData:
    recipes: dict[int, Recipe]
    items: dict[int, ItemInfo]
    trainer_ranks: dict[int, list[Rank]]
    vendor_prices: dict[int, int]
    quest_items: set[int]
    tool_items: dict[int, int]  # category -> base item
    tool_masks: dict[int, int]  # category -> mask
    item_tool_category: dict[int, int]  # item -> category

    def satisfies(self, item_id: int, category: int) -> bool:
        cat = self.item_tool_category.get(item_id)
        if cat is None or category not in self.tool_masks or cat not in self.tool_masks:
            return False
        need = self.tool_masks[category]
        return self.tool_masks[cat] & need == need

    def name(self, item_id: int) -> str:
        i = self.items.get(item_id)
        return i.name if i else f"item {item_id}"


SEEN_REQUIREMENTS = Path(__file__).resolve().parent / "data_static" / "seen_requirements.toml"


def load_seen_requirements(path: Path = SEEN_REQUIREMENTS) -> dict[int, int]:
    """spell -> the highest skill the recipe was seen learnable at in game, below its inferred Classic
    requirement (`seen_requirements.toml`)."""
    with open(path, "rb") as f:
        return {int(row["spell_id"]): int(row["skill"]) for row in tomllib.load(f).get("seen", [])}


def safe_requirements(gd: GameData, skip: Iterable[int] = (), seen: dict[int, int] | None = None) -> GameData:
    """The game data as the planner plans with it: a trainer recipe whose inferred skill is above the
    Forever requirement needs the inferred one, so the route works wherever the trainer sets the bar.
    The Forever value stays in `listed_skill`. Other sources are unchanged, and so is `gd` (a copy).
    skip: spells the planner turns into quest recipes (the quest plans), which are left alone.
    seen: spell -> a skill it was seen learnable at in game (default: `seen_requirements.toml`); an
    inferred skill above it is wrong for Forever, so that recipe keeps the Forever requirement."""
    skip = set(skip)
    seen = load_seen_requirements() if seen is None else seen
    recipes = {}
    for spell, r in gd.recipes.items():
        if (spell not in skip and r.source == "trainer" and r.listed_skill is None and r.inferred_skill
                and r.inferred_skill > r.required_skill and r.inferred_skill <= seen.get(spell, r.inferred_skill)):
            r = dataclasses.replace(r, required_skill=r.inferred_skill, listed_skill=r.required_skill)
        recipes[spell] = r
    return dataclasses.replace(gd, recipes=recipes)


def listed_requirements(gd: GameData) -> GameData:
    """`safe_requirements` undone: every recipe back at the requirement the Forever data lists."""
    recipes = {spell: dataclasses.replace(r, required_skill=r.listed_skill, listed_skill=None)
               if r.listed_skill is not None else r for spell, r in gd.recipes.items()}
    return dataclasses.replace(gd, recipes=recipes)


class GameDataError(ValueError):
    """A game data file that is not what its name says, with what to do about it."""


def check_file(path: Path, name: str) -> None:
    """Raise ValueError unless `path` looks like the source file `name` (see EXPECTED)."""
    kind, wanted = EXPECTED[name]
    try:
        with open(path, encoding="utf-8", newline="") as f:
            if kind == "csv":
                rows = csv.reader(f)
                header = next(rows, [])
                missing = [c for c in wanted if c not in header]
                if not missing and next(rows, None) is None:
                    raise ValueError("a header and no rows")
            else:
                text = f.read()
                missing = [t for t in wanted
                           if not re.search(r"(?:ns|QuestieDB)\." + re.escape(t) + r"\s*=", text)]
    except UnicodeDecodeError:
        missing = list(wanted)
    if missing:
        what = "columns" if kind == "csv" else "tables"
        raise ValueError(f"no {', '.join(missing)} {what}")


def fetch_all(force: bool = False, dest: Path | None = None, only: Iterable[str] | None = None,
              skip: Iterable[str] = ()) -> None:
    """Download what is not cached yet: every source, or just `only`, or all but `skip`.
    A download that is not game data (an error page, say) is not kept: GameDataError names it."""
    dest = Path(dest) if dest is not None else settings.paths().gamedata
    dest.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        if (only is not None and name not in only) or name in skip:
            continue
        p = dest / name
        if p.exists() and not force:
            continue
        req = urllib.request.Request(url, headers={"User-Agent": f"yap-forever/{__version__}"})
        part = p.with_name(p.name + ".part")
        try:
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    body = r.read()
            except urllib.error.URLError:
                raise
            except (OSError, http.client.HTTPException) as e:  # cut off midway: a network problem
                raise urllib.error.URLError(f"the download of {name} was cut off ({type(e).__name__})") from None
            part.write_bytes(body)
            try:
                check_file(part, name)
            except ValueError as e:
                raise GameDataError(f"the download of {name} is not game data ({e}): nothing was saved; "
                                    "try again later, and if it keeps failing, report it") from None
            os.replace(part, p)  # a cut-off or bad download never takes the real name
        finally:
            part.unlink(missing_ok=True)
        print(f"downloaded {name}")


def prune_stale(dest: Path) -> None:
    """Remove the copies of other pins next to `dest` (cache/gamedata/<PIN_KEY>): the files of the flat
    layout used before the pins were in the path, and other pin folders. Nothing else is touched, and
    nothing at all unless `dest` is a pin folder inside a `gamedata` folder."""
    root = dest.parent
    if root.name != "gamedata" or not _PIN_DIR.fullmatch(dest.name):
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for f in entries:
        try:
            if f.is_file() and (f.name in SOURCES or f.name.removesuffix(".part") in SOURCES):
                f.unlink()
            elif f.is_dir() and f != dest and _PIN_DIR.fullmatch(f.name):
                shutil.rmtree(f)
        except OSError:  # housekeeping only: a copy that can't be removed now is tried again next time
            continue


@contextmanager
def _reading(path: Path) -> Iterator[None]:
    """Turn a file that fails to load into a GameDataError that names it and says what to do."""
    try:
        yield
    except GameDataError:
        raise
    except (KeyError, ValueError, IndexError, TypeError, AttributeError, UnicodeDecodeError) as e:
        raise GameDataError(f"the game data file {path} is damaged ({type(e).__name__}: {e}): "
                            "delete it and run the plan again to download it fresh") from None


def _lua(path: Path, name: str):
    return parse(extract_table(path.read_text(encoding="utf-8"), name))


def _rows(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def item_names(path: Path) -> dict[int, str]:
    return {int(r["ID"]): r["Display_lang"] for r in _rows(path)}


def _flatten_names(tree) -> dict[int, str]:
    out = {}
    for v in (tree.values() if isinstance(tree, dict) else tree):
        if isinstance(v, dict):
            out.update({int(spell): name for name, spell in v.items()})
    return out


def _quest_items(quests: dict) -> set[int]:
    items = set()
    for q in quests.values():
        if not isinstance(q, list):
            continue
        objectives = q[9] if len(q) > 9 else None
        if isinstance(objectives, list) and len(objectives) > 2 and isinstance(objectives[2], list):
            items.update(o[0] for o in objectives[2] if isinstance(o, list) and o and isinstance(o[0], int))
        required = q[20] if len(q) > 20 else None
        if isinstance(required, list):
            items.update(i for i in required if isinstance(i, int))
    return items


def load_gamedata(d: Path | None = None, professions: Iterable[int] = (BS, ENCH)) -> GameData:
    """Game data with the recipes (and starter recipes) of `professions` only."""
    professions = set(professions)
    d = Path(d) if d is not None else settings.paths().gamedata
    for name in ("Recipes.lua", "Thresholds.lua", "Trainer.lua", "Vendor.lua", "foreverQuestDB.lua",
                 "ItemSparse.csv", "Item.csv", "SpellTotems.csv", "TotemCategory.csv", "SkillLineAbility.csv"):
        with _reading(d / name):
            check_file(d / name, name)
    with _reading(d / "Recipes.lua"):
        recipes_src = (d / "Recipes.lua").read_text(encoding="utf-8")
        data = parse(extract_table(recipes_src, "RecipeData"))
        scrolls = parse(extract_table(recipes_src, "RecipeScrolls"))
        names = _flatten_names(parse(extract_table(recipes_src, "RecipeNames")))
    with _reading(d / "Thresholds.lua"):
        thresholds = _lua(d / "Thresholds.lua", "Thresholds")
    with _reading(d / "Trainer.lua"):
        trainer_src = (d / "Trainer.lua").read_text(encoding="utf-8")
        fees = parse(extract_table(trainer_src, "TrainerFees"))
        ranks = parse(extract_table(trainer_src, "TrainerRanks"))
        try:
            inferred = parse(extract_table(trainer_src, "TrainerInferred"))
        except KeyError:  # a Trainer.lua from before the table existed
            inferred = {}
        trainer_ranks = fill_rank_levels({int(k): [Rank(*map(int, x)) for x in v] for k, v in ranks.items()})
    with _reading(d / "Vendor.lua"):
        vendor = _lua(d / "Vendor.lua", "VendorPrices")
        vendor_prices = {int(k): int(v) for k, v in vendor.items()}
    with _reading(d / "SkillLineAbility.csv"):
        starters = {int(r["Spell"]) for r in _rows(d / "SkillLineAbility.csv")
                    if int(r["SkillLine"]) in professions and r["AcquireMethod"] == "1"}

    with _reading(d / "SpellTotems.csv"):
        tools: dict[int, list[int]] = {}
        for r in _rows(d / "SpellTotems.csv"):
            cats = [int(r[k]) for k in ("RequiredTotemCategoryID_0", "RequiredTotemCategoryID_1") if int(r[k])]
            if cats:
                tools[int(r["SpellID"])] = cats

    with _reading(d / "Recipes.lua"):
        recipes = {}
        for spell, rd in data.items():
            if rd.get("skillLine") not in professions or spell not in thresholds:
                continue
            t = tuple(int(x) for x in thresholds[spell])
            req = [t[0]]
            source, fee, scroll = "unknown", 0, None
            if spell in fees:
                source, fee = "trainer", int(fees[spell][0])
                req.append(int(fees[spell][1]))
            elif spell in scrolls:
                source, scroll = "scroll", int(scrolls[spell][0])
                req.append(int(scrolls[spell][1]))
            elif spell in starters:
                source = "starter"
            out = rd.get("output")
            recipes[spell] = Recipe(
                spell_id=spell, name=names.get(spell, f"spell {spell}"), skill_line=rd["skillLine"],
                reagents={int(x["itemID"]): int(x["quantity"]) for x in rd.get("reagents", [])},
                output=(int(out["itemID"]), out["quantity"]) if out else None,
                thresholds=t, required_skill=max(req), source=source, fee=fee,
                scroll_item=scroll, tools=tools.get(spell, []),
                inferred_skill=int(inferred[spell]) if spell in inferred else None)

    with _reading(d / "Item.csv"):
        classes = {int(r["ID"]): int(r["ClassID"]) for r in _rows(d / "Item.csv")}
    items, item_cat = {}, {}
    with _reading(d / "ItemSparse.csv"):
        for r in _rows(d / "ItemSparse.csv"):
            i = int(r["ID"])
            items[i] = ItemInfo(i, r["Display_lang"], int(r["OverallQualityID"]), int(r["ItemLevel"]),
                                classes.get(i, -1), int(r["SellPrice"]), int(r["BuyPrice"]),
                                bool(int(r.get("Flags_0") or 0) & NO_DISENCHANT_FLAG),
                                max(1, int(r.get("Stackable") or 1)),
                                int(r["Bonding"]) if r.get("Bonding") not in (None, "") else None)
            cat = int(r.get("TotemCategoryID") or 0)
            if cat:
                item_cat[i] = cat
    with _reading(d / "TotemCategory.csv"):
        masks = {int(r["ID"]): int(r["TotemCategoryMask"]) for r in _rows(d / "TotemCategory.csv")}
    tool_items = {}
    for item, cat in sorted(item_cat.items()):
        tool_items.setdefault(cat, item)  # lowest ID = the basic item of that category

    with _reading(d / "foreverQuestDB.lua"):
        quest_items = _quest_items(_lua(d / "foreverQuestDB.lua", "questData"))

    return GameData(
        recipes=recipes, items=items,
        trainer_ranks=trainer_ranks,
        vendor_prices=vendor_prices,
        quest_items=quest_items,
        tool_items=tool_items, tool_masks=masks, item_tool_category=item_cat)


def checks_report(gd: GameData, cap: int = 225) -> str:
    """The spec's 'verify from the data first' list, as markdown."""
    lines = ["# Game data checks", ""]
    bs = sorted((r for r in gd.recipes.values() if r.skill_line == BS and r.required_skill <= cap),
                key=lambda r: r.required_skill)
    greens = [r for r in bs if r.output and gd.items.get(r.output[0]) and gd.items[r.output[0]].quality == 2]
    lines += [f"## Blacksmithing crafts of uncommon quality up to {cap} ({len(greens)})", ""]
    for r in greens:
        i = gd.items[r.output[0]]
        q = " (quest item)" if i.id in gd.quest_items else ""
        lines.append(f"- {r.required_skill}: {r.name} — ilvl {i.item_level}, source {r.source}{q}")
    ench = [r for r in gd.recipes.values() if r.skill_line == ENCH and r.required_skill <= cap]
    cats = sorted({c for r in ench for c in r.tools})
    lines += ["", f"## Tools needed by Enchanting recipes up to {cap}", ""]
    for c in cats:
        item = gd.tool_items.get(c)
        maker = [r.name for r in gd.recipes.values() if item and r.output and r.output[0] == item]
        users = sum(1 for r in ench if c in r.tools)
        lines.append(f"- {gd.name(item) if item else c}: needed by {users} recipes; made by {', '.join(maker) or 'no recipe here'}")
    with_items = [r for r in ench if r.output and gd.items.get(r.output[0])]
    lines += ["", f"## Enchanting recipes up to {cap} that make an item ({len(with_items)})", ""]
    lines += [f"- {r.required_skill}: {r.name} → {gd.name(r.output[0])}" for r in sorted(with_items, key=lambda r: r.required_skill)]
    unknown = [r for r in gd.recipes.values() if r.source == "unknown" and r.required_skill <= cap]
    lines += ["", f"## Recipes up to {cap} with no known source ({len(unknown)})", "",
              "These are excluded unless favor.toml lists them.", ""]
    lines += [f"- {PROFESSIONS[r.skill_line]}: {r.name}" for r in sorted(unknown, key=lambda r: (r.skill_line, r.name))]
    return "\n".join(lines) + "\n"


def usage_prog(os_name: str = os.name) -> str:
    """The command as the player types it on their system, for the usage line."""
    return f"{'py -3' if os_name == 'nt' else 'python3'} -m yap_forever.gamedata"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=usage_prog(),
        description="Download the pinned game data into your cache (what is already there is kept).")
    parser.add_argument("--fetch", action="store_true", help="download again even when the files are cached")
    parser.add_argument("--checks", action="store_true",
                        help="also write reports/data-checks.md, a list of what the data says about the recipes")
    args = parser.parse_args(argv)
    fetch_all(force=args.fetch)
    if args.checks:
        out = settings.paths().reports / "data-checks.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(checks_report(load_gamedata()), encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
