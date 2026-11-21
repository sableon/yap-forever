"""Merchant's Favor recipes to craft once ("You could also make"), apart from the route.

Favor recipes are personal-use rewards: the route never levels with them (planner._Route._may_use), and the
guide and the report suggest the ones the character could make now for itself. A recipe is suggested when:
- it crafts an item whose required level is near the character's (`level_ok`); an enchant (no crafted item)
  has no level test;
- the character's skill is at least the recipe's Favor skill, and its Favor at least the price;
- its materials, taken from the bank, then mailed by the group's other characters, the rest bought at today's
  AH or vendor price, cost at most the group's gold (before the route);
- it is not the profession's craft-once goal (the route plans that one).
"""
import math
from dataclasses import dataclass, field

from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import gold as gold_text, recipe_name
from yap_forever.planner import apply_favor
from yap_forever.shared import allocate, mail_text

LEVEL_WINDOW = 5  # levels either side of the character's level an item may need
LATE_WINDOW = 3  # the window from character level LATE_FROM on
LATE_FROM = 46
GUIDE_LIMIT = 6  # items, then enchants, the guide lists of each kind; the rest are counted ("and N more.")
INTRO = ("Merchant's Favor recipes to craft once for yourself, if you don't have the item yet. They are not part of "
         "the route, its shopping list or its gold.")
HEADING = "## You could also make"
WHERE = {("ah",): "on the AH", ("vendor",): "from a vendor", ("ah", "vendor"): "on the AH and from a vendor"}


@dataclass(frozen=True)
class Suggestion:
    spell: int
    name: str
    profession: int
    skill: int  # the recipe's Favor skill
    level: int | None  # the crafted item's required level; None for an enchant
    favor: int  # its Favor price
    gold: float  # copper: the materials not held, at today's AH or vendor price
    from_bank: dict[int, int]  # item -> count from your bank
    from_mail: dict[int, list[tuple[str, int]]]  # item -> (character, count) mailed by your other characters
    bought: tuple[str, ...] = field(default=())  # where the rest is bought: "ah", "vendor" (in that order)


def level_ok(char_level: int, item_level: int | None) -> bool:
    """The item's required level is within LEVEL_WINDOW of the character's level (LATE_WINDOW from LATE_FROM on).
    An unknown level (None) is never within it."""
    if item_level is None:
        return False
    return abs(char_level - item_level) <= (LATE_WINDOW if char_level >= LATE_FROM else LEVEL_WINDOW)


def levels_known(gd) -> bool:
    """The game data gives items' required levels (a cache without the column gives none)."""
    return any(i.required_level is not None for i in gd.items.values())


def _materials(r, stock, valuer, shared):
    """(gold, from bank, from mail, bought where) for one craft of r, or None when a reagent can't be had."""
    gold, bank, mail, where = 0.0, {}, {}, set()
    for item, q in r.reagents.items():
        held = min(q, stock.items.get(item, 0))
        if held > 0:
            bank[item] = held
        rest = q - held
        if rest > 0:
            senders = allocate(shared, item, math.ceil(rest))
            if senders:
                mail[item] = senders
                rest -= sum(n for _who, n in senders)
        if rest > 0:
            opt = valuer.buy_option(item, rest, 0)
            if opt is None:
                return None
            gold += opt[1]
            where.add(opt[0])
    return gold, bank, mail, tuple(k for k in ("ah", "vendor") if k in where)


def suggest(gd, favor, stock, valuer, gold_copper, shared, goal_spells) -> list[Suggestion]:
    """Every suggestion, in the order listed. favor: the character's favor.FavorData; stock: its
    config.Stock (skills, level, Favor and bank); valuer: prices (costmodel.Valuer.buy_option); gold_copper: the
    group's gold (shared.Budget.copper, else the stock's cash_gold); shared: the other characters' mailable items,
    by name; goal_spells: the craft-once goals, left out. Items nearest the character's level first, then by Favor
    price; then the enchants, by Favor price."""
    out = []
    for spell, r in apply_favor(gd.recipes, favor).items():
        if r.source != "favor" or spell not in favor.recipes or spell in goal_spells:
            continue
        price = favor.recipes[spell]
        if stock.skills.get(r.skill_line, 0) < r.required_skill or price > stock.favor:
            continue
        level = None
        if r.output:
            info = gd.items.get(r.output[0])
            level = info.required_level if info else None
            if not level_ok(stock.level, level):
                continue
        mats = _materials(r, stock, valuer, shared)
        if mats is None or mats[0] > gold_copper:
            continue
        out.append(Suggestion(spell, recipe_name(spell, r.name, gd), r.skill_line, r.required_skill, level, price,
                              *mats))
    out.sort(key=lambda s: (s.level is None, abs(stock.level - s.level) if s.level is not None else 0, s.favor,
                            s.name, s.spell))
    return out


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _row(s: Suggestion, gd, favor_owned: int) -> str:
    what = PROFESSIONS.get(s.profession, str(s.profession)) + f" {s.skill}"
    if s.level is not None:
        what += f", for level {s.level}"
    held = []
    if s.from_bank:
        counts = sorted((gd.name(i), n) for i, n in s.from_bank.items())
        held.append(_and([f"{n:g} {name}" for name, n in counts]) + " from your bank")
    if s.from_mail:
        held.append(mail_text(s.from_mail, gd.name))
    if s.gold > 0:
        mats = " " + ", ".join([f"about {gold_text(s.gold)} {WHERE[s.bought]}", *held])
    else:
        mats = ": " + ", ".join(held)
    return f"- **{s.name}** ({what}): {s.favor} of your {favor_owned} Favor; materials{mats}."


def lines(found: list[Suggestion], gd, favor_owned: int, heading: str = HEADING, limit: int | None = None) -> list[str]:
    """The "You could also make" block for the suggestions `found` (suggest): the guide's section after the route, with
    at most `limit` items, then at most `limit` enchants, each kind cut with "and N more."; the report's, inside
    "Merchant's Favor", under a bold heading and complete (limit None). [] when there is nothing to suggest."""
    if not found:
        return []
    out = [heading, "", INTRO, ""]
    for kind in ([s for s in found if s.level is not None], [s for s in found if s.level is None]):
        if not kind:
            continue
        shown = kind if limit is None else kind[:limit]
        if out[-1] != "":
            out.append("")
        out += [_row(s, gd, favor_owned) for s in shown]
        if len(kind) > len(shown):
            out += ["", f"and {len(kind) - len(shown)} more.", ""]
    return out if out[-1] == "" else [*out, ""]
