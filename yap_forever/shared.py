"""Characters on one ruleset and faction share their gold and can mail each other items.

A character's group is its (ruleset, faction); the auction house belongs to the group too. Gold has no
character-bound form, and every item except those bound on pickup (or a quest item) can be mailed, so what
the other characters of a group hold is stock the planner may draw on by mail (see `Group`).
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

from yap_forever import profile as profile_mod
from yap_forever.config import Stock, load_stock

COPPER_PER_GOLD = 10000


def mailable(items: dict[int, int], gd) -> dict[int, int]:
    """The part of a character's items that can be mailed: known to the game data and not bound on pickup."""
    return {i: n for i, n in items.items() if n > 0 and (info := gd.items.get(i)) is not None and info.mailable}


def allocate(shared: dict[str, dict[int, int]], item: int, n: int) -> list[tuple[str, int]]:
    """Who mails n of an item: each other character in name order gives what it holds, until n is met."""
    out = []
    for name in sorted(shared):
        take = min(n, shared[name].get(item, 0))
        if take > 0:
            out.append((name, take))
            n -= take
        if n <= 0:
            break
    return out


def mail_used(shared: dict[str, dict[int, int]], left: dict[int, float]) -> dict[int, list[tuple[str, int]]]:
    """item -> (character, count) for what a plan took from the shared pool; `left` is what the pool still
    held afterwards. Counts are whole items (a plan counts in fractions of a craft)."""
    total: dict[int, int] = {}
    for items in shared.values():
        for i, n in items.items():
            total[i] = total.get(i, 0) + n
    out = {}
    for i, n in total.items():
        used = n - left.get(i, 0)
        if used > 1e-9:
            out[i] = allocate(shared, i, math.ceil(used - 1e-9))
    return out


SHARED_NOTE = ("Items your other characters mail you are counted from their stock as it is now, with nothing "
               "reserved: a plan for another character may count the same items.")


def mail_text(used: dict[int, list[tuple[str, int]]], name) -> str:
    """'3 Iron Bar (mail from Ann), 2 Iron Bar (mail from Bob)': what the plan takes from the other
    characters, items by name, sources in name order. name: item id -> its name."""
    rows = sorted((name(i), who, n) for i, sources in used.items() for who, n in sources)
    return ", ".join(f"{n} {item} (mail from {who})" for item, who, n in rows)


@dataclass(frozen=True)
class Budget:
    """The gold a group shares, in copper, and where the figure comes from."""
    copper: int
    label: str  # "2/alliance"
    is_sum: bool = False  # no [gold] entry: the sum of the characters' `cash_gold` of several characters
    shared: bool = True  # False: one character's own `cash_gold`, with no [gold] entry and nobody to share with


@dataclass
class Group:
    """What the other characters of one character's ruleset and faction bring to a plan."""
    ruleset: int
    faction: str
    gold: float | None = None  # profile.toml's [gold] entry for the group, in gold
    others: dict[str, Stock] = field(default_factory=dict)  # the other characters with a stock file
    skipped: list[tuple[Path, str]] = field(default_factory=list)  # their stock files that could not be read

    @property
    def label(self) -> str:
        return profile_mod.group_label((self.ruleset, self.faction))

    def shared_items(self, gd) -> dict[str, dict[int, int]]:
        """Each other character's mailable items, by name (characters with none are left out)."""
        out = {name: items for name in sorted(self.others)
               if (items := mailable(self.others[name].items, gd))}
        return out

    def budget(self, stock: Stock) -> Budget:
        """The group's gold: the [gold] entry, else the sum of every stock file's `cash_gold` (the
        character being planned included). With no entry and no other character, it is this character's
        own figure: not shared, and not a sum."""
        if self.gold is not None:
            return Budget(round(self.gold * COPPER_PER_GOLD), self.label)
        alone = not self.others
        return Budget(stock.cash + sum(s.cash for s in self.others.values()), self.label, not alone, not alone)

    def notes(self) -> list[str]:
        """One line for each mate's stock file that was left out because it could not be read."""
        return [f"{path} (a character of your {self.label} group) can't be read ({why}): that character's "
                "items and gold are left out of this plan." for path, why in self.skipped]


def load_group(paths, prof: "profile_mod.Profile", character: str) -> Group:
    """The group of `character`: its [gold] entry and the stock files of its other members.

    A member without a stock.toml contributes nothing. A member's file that can't be read is left out and
    named in the notes (`Group.notes`); it does not stop the plan."""
    group = prof.group_of(character)
    out = Group(group[0], group[1], prof.gold.get(group))
    for name in sorted(prof.characters):
        if name == character or prof.group_of(name) != group:
            continue
        path = Path(paths.character(name)) / "stock.toml"
        if not path.exists():
            continue
        try:
            out.others[name] = load_stock(path)
        except (ValueError, KeyError, TypeError, OSError) as e:
            why = getattr(e, "detail", None) or str(e) or type(e).__name__  # the path is in the note
            out.skipped.append((path, why))  # said in the notes; the plan goes on
    return out
