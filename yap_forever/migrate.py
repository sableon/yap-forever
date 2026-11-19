"""Move a personal planner folder (the layout before yap-forever) into the home layout.

Never touches credentials: the player copies those themselves.
"""
import json
import shutil
import tomllib
from pathlib import Path

from yap_forever import profile
from yap_forever.config import PROFESSION_IDS
from yap_forever.settings import Paths


def _copy(src: Path, dst: Path, actions: list[str]) -> None:
    if not src.exists():
        actions.append(f"skipped {src} (not found)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    actions.append(f"copied {src} -> {dst}")


def _add_goals(stock: Path, actions: list[str]) -> None:
    """Older stock files plan Blacksmithing + Enchanting to `target`; say so in a [goals] table."""
    if not stock.exists():
        return
    text = stock.read_text(encoding="utf-8")
    d = tomllib.loads(text)
    if "goals" in d:
        return
    target = int(d.get("target", 225))
    sep = "" if text.endswith("\n") else "\n"
    stock.write_text(f"{text}{sep}\n[goals]\nblacksmithing = {target}\nenchanting = {target}\n",
                     encoding="utf-8")
    actions.append(f"added [goals] (Blacksmithing and Enchanting to {target}) to {stock}")


FILL_IN = "level, [skills] and [goals]; gold goes under [gold] in profile.toml"
_PROFESSION_NAMES = {v: k for k, v in PROFESSION_IDS.items()}


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"can't read {path}: {e}") from None


def is_bags_file(path: Path) -> bool:
    """A bags file (a character's bag slots and items) has a `profs` key; a stock file has none."""
    return "profs" in _read(path)


def _count(d: dict, key: str, what: str) -> int | None:
    if key not in d:
        return None
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ValueError(f"{what}: {key} must be a whole number, 0 or more (got {v!r})")
    return v


def bags_to_stock(bags: Path, stock: Path) -> bool:
    """Write a stock file from a bags file: bag_slots, reagent_slots and [items] carry over, the
    professions become commented lines under [skills] and [goals], and a top comment names what to fill
    in. Returns False, writing nothing, when `stock` exists; the bags file is never touched.
    Raises ValueError for a bags file that can't be read."""
    bags, stock = Path(bags), Path(stock)
    if stock.exists():
        return False
    d = _read(bags)
    what = str(bags)
    profs = d.get("profs", [])
    if not isinstance(profs, list) or not all(isinstance(p, (str, int)) and not isinstance(p, bool)
                                              for p in profs):
        raise ValueError(f"{what}: profs must be a list of profession names")
    names = [_PROFESSION_NAMES.get(p, str(p)) if isinstance(p, int) else " ".join(p.lower().split()) for p in profs]
    slots = {k: _count(d, k, what) for k in ("bag_slots", "reagent_slots")}
    raw = d.get("items", {})
    items: dict[int, int] = {}
    try:
        for k, v in raw.items():
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError
            if int(k) in items:
                raise ValueError(f"{what}: [items] lists item {int(k)} twice")
            items[int(k)] = v
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError(str(e) or f"{what}: [items] must be item ID = whole number count") from None
    out = [f"# Made from {bags.name} by yap-forever. Check before you plan: {FILL_IN} "
           "(gold is shared by the characters of one ruleset and faction).",
           "# level = <your level>"]
    out += [f"{k} = {v}" for k, v in slots.items() if v is not None]
    out += ["", "[items]"] + [f"{k} = {v}" for k, v in items.items()]
    out += ["", "[skills]"] + [f"# {n} = <current skill>" for n in names]
    out += ["", "[goals]"] + [f"# {n} = <goal>" for n in names]
    stock.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(stock, "x", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except FileExistsError:
        return False
    return True


def migrate(data_dir: Path, dest: Paths, characters: dict[str, Path], region: str = "eu",
            ruleset: int = 2, faction: str = "alliance") -> list[str]:
    """Give every character a stock.toml, copy house, prices and game data, and write a profile if
    there is none. characters: name -> a stock file (copied) or a bags file (converted); a file with a
    `profs` key is a bags file. A file that can't be read raises ValueError before anything is written.

    region, ruleset and faction go into the new profile and the saved house."""
    actions: list[str] = []
    kinds = {name: is_bags_file(f) if Path(f).exists() else None for name, f in characters.items()}
    for name, src in characters.items():
        src, dst = Path(src), dest.character(name) / "stock.toml"
        if kinds[name]:
            if bags_to_stock(src, dst):
                actions.append(f"converted {src} -> {dst} (check {FILL_IN})")
            else:
                actions.append(f"kept {dst}")
        elif dst.exists():
            actions.append(f"kept {dst}")
        else:
            _copy(src, dst, actions)
            _add_goals(dst, actions)
    house_file = Path(data_dir) / "house.json"
    if house_file.exists():
        house = int(json.loads(house_file.read_text(encoding="utf-8"))["house"])
        profile.save_house(dest.house, house, region, ruleset)
        actions.append(f"saved house {house} -> {dest.house}")
    _copy(Path(data_dir) / "prices.json", dest.prices, actions)
    gd = Path(data_dir) / "gamedata"
    if gd.is_dir():
        for f in sorted(gd.iterdir()):
            if f.is_file():
                _copy(f, dest.gamedata / f.name, actions)
    if dest.profile.exists():
        actions.append(f"kept {dest.profile}")
    else:
        # Quoted keys: character names may have spaces or accents, which bare TOML keys can't.
        chars = "".join(f'\n[characters.{json.dumps(n, ensure_ascii=False)}]\nfavor_standing = "Neutral"\n'
                        for n in characters)
        dest.profile.parent.mkdir(parents=True, exist_ok=True)
        dest.profile.write_text(f'region = "{region}"\nruleset = {ruleset}\nfaction = "{faction}"\n' + chars,
                                encoding="utf-8")
        actions.append(f"wrote {dest.profile}")
    return actions
