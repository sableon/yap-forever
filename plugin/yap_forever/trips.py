"""Trips away from home: rank trainers in set towns, recipe trips back to them, vendor patterns, the Favor vendor.

A trainer teaches the recipes up to its rank's cap (`recipe_rank_cap`), so every trainer visit learns the
recipes the route needs later that its rank teaches and the skill allows (`visits`); a recipe that no visit
can teach makes a visit of its own: a trip for an Artisan or Master recipe, a capital stop below. Ranks
below 225 are not trips (Expert and Journeyman trainers are in the main cities), nor AH patterns (they come
by mail).
"""
from dataclasses import dataclass, field

from yap_forever.gamedata import PROFESSIONS
from yap_forever.trainers import RANK_BY_CAP

REMOTE_RANK = 225  # ranks to 225 (Artisan) and 300 (Master) are trained in set towns
MAX_TRIP_ALTS = 3
RANK_CAPS = tuple(sorted(RANK_BY_CAP))  # 75, 150, 225, 300: Journeyman, Expert, Artisan, Master


def recipe_rank_cap(required_skill: int) -> int:
    """The cap of the lowest trainer rank that teaches a recipe: the lowest rank cap at or above its required
    skill (75, 150, 225 or 300). A trainer teaches the recipes up to its own cap, lower ranks' included
    (one sighting: an Expert trainer lacks a 175 recipe that an Artisan teaches); this is the one place
    that says so."""
    return next((c for c in RANK_CAPS if c >= required_skill), RANK_CAPS[-1])


@dataclass
class Visit:
    """A trainer visit the route makes, and the trainer recipes learned there.
    kind: "rank" (a rank training: `remote` for Artisan and Master, else a capital), "recipe" (a trip to an
    Artisan or Master trainer only to learn recipes) or "city" (the same, at an Expert or Journeyman trainer
    in a capital). rank_cap: the cap of the trainer's rank. learn: trainer recipes the route needs later
    whose required skill is reached by `skill` (learn ahead). if_missing: recipes already reachable at the
    start skill (the stock doesn't say which are known), listed at the first visit that teaches them.
    fallback: spell -> the cap of the lowest rank that teaches it, for recipes below this trainer's rank."""
    profession: int
    skill: int
    rank_cap: int
    remote: bool
    kind: str
    learn: list[int] = field(default_factory=list)
    if_missing: list[int] = field(default_factory=list)
    fallback: dict[int, int] = field(default_factory=dict)


def _visits(plan, gd, start_skills: dict[int, int]) -> tuple[list[Visit], dict[int, list[int]]]:
    """(visits in skill order, profession -> recipes to know before the first visit that teaches them)."""
    ranks = [Visit(prof, s, cap, cap >= REMOTE_RANK, "rank") for prof, s, cap, _fee in plan.ranks]
    out = sorted(ranks, key=lambda v: v.skill)
    learns = sorted(((prof, s, spell, gd.recipes[spell].required_skill) for prof, s, spell, how in plan.learn_log
                     if how == "trainer" and spell in gd.recipes), key=lambda x: x[1])
    known: list[tuple[int, int, int, int]] = []

    def first(prof, req, rank, at):
        return next((v for v in out if v.profession == prof and req <= v.skill <= at and v.rank_cap >= rank), None)

    def add(v, into, spell, rank):
        into.append(spell)
        if rank < v.rank_cap:
            v.fallback[spell] = rank

    for prof, s, spell, req in learns:
        if req <= max(1, start_skills.get(prof, 1)):  # reachable at the start: never a visit of its own
            known.append((prof, s, spell, req))
            continue
        rank = recipe_rank_cap(req)
        v = first(prof, req, rank, s)
        if v is None:
            v = Visit(prof, s, rank, rank >= REMOTE_RANK, "recipe" if rank >= REMOTE_RANK else "city")
            out.append(v)
            out.sort(key=lambda v: v.skill)  # stable: a visit made at a rank training's skill comes after it
        add(v, v.learn, spell, rank)
    before: dict[int, list[int]] = {}
    for prof, s, spell, req in known:
        rank = recipe_rank_cap(req)
        v = first(prof, req, rank, s)
        if v is None:
            before.setdefault(prof, []).append(spell)
        else:
            add(v, v.if_missing, spell, rank)
    return out, before


def visits(plan, gd, start_skills: dict[int, int]) -> list[Visit]:
    """The trainer visits of the route, in skill order: each rank training, and a visit for each trainer
    recipe that no earlier visit can teach (see Visit). start_skills: profession -> the route's start skill."""
    return _visits(plan, gd, start_skills)[0]


def before_start(plan, gd, start_skills: dict[int, int]) -> dict[int, list[int]]:
    """profession -> trainer recipes already reachable at the start skill that the route uses before any
    visit that teaches them: the player should know them before starting."""
    return _visits(plan, gd, start_skills)[1]


@dataclass(frozen=True)
class Trip:
    skill: int
    profession: int
    kind: str  # "rank", "recipe" (back to a remote trainer for recipes), "vendor" or "favor"
    what: str
    spell: int | None = None
    cost: float = 0
    cap: int = 0  # the skill cap a rank stop trains to; a recipe trip's trainer rank
    spells: tuple[int, ...] = ()  # a recipe trip's recipes
    visit: Visit | None = None  # a rank or recipe trip's trainer visit

    @property
    def key(self) -> int | tuple[int, ...] | None:
        """What trip_alternatives keys the trip by: its recipe, or a recipe trip's recipes."""
        return self.spells or self.spell


def trips(plan, gd, start_skills: dict[int, int]) -> list[Trip]:
    """The trips away from home, in skill order. start_skills: profession -> the route's start skill."""
    out = []
    for v in visits(plan, gd, start_skills):
        name = PROFESSIONS.get(v.profession, v.profession)
        if v.kind == "rank" and v.remote:
            fee = next(f for prof, s, cap, f in plan.ranks if (prof, s, cap) == (v.profession, v.skill, v.rank_cap))
            out.append(Trip(v.skill, v.profession, "rank", f"{name} rank to {v.rank_cap}", None, fee, v.rank_cap,
                            visit=v))
        elif v.kind == "recipe":
            names = ", ".join(gd.recipes[s].name for s in v.learn)
            out.append(Trip(v.skill, v.profession, "recipe", names, None, sum(gd.recipes[s].fee for s in v.learn),
                            v.rank_cap, tuple(v.learn), v))
    for prof, s, spell, how in plan.learn_log:
        if how in ("vendor", "favor"):
            r = gd.recipes.get(spell)
            name = r.name if r else str(spell)
            cost = gd.vendor_prices.get(r.scroll_item, 0) if r and how == "vendor" and r.scroll_item else 0
            out.append(Trip(s, prof, how, name, spell, cost))
    return sorted(out, key=lambda t: (t.skill, t.kind != "vendor" and t.kind != "favor", t.profession))


def trip_alternatives(base, inputs, mode) -> dict[int | tuple[int, ...], float | None]:
    """What the route costs more without a trip's recipes, in the route's own measure, by Trip.key; None when
    the targets can't be reached without them. For every recipe trip, and the costliest few vendor and
    Favor trips. inputs: the plan.PlanInputs the route was planned from."""
    from yap_forever.plan import plan_route  # plan imports this module

    measure = (lambda p: p.cash_total) if mode == "gold" else (lambda p: p.economic_total)
    goals = set(inputs.craft_once.values())  # the goal recipe can't be skipped
    found = trips(base, inputs.gd, inputs.stock.skills)
    picks = sorted((t for t in found if t.spell is not None and t.spell not in goals),
                   key=lambda t: -t.cost)[:MAX_TRIP_ALTS]
    out: dict[int | tuple[int, ...], float | None] = {}
    for t in [t for t in found if t.kind == "recipe"] + picks:
        if goals & set(t.spells):  # a recipe trip for the goal recipe can't be skipped either
            out[t.key] = None
            continue
        alt = plan_route(inputs, mode, exclude=frozenset(t.spells or {t.spell}))
        reached = all(alt.final_skill.get(p, 0) >= base.final_skill.get(p, 0) for p in inputs.caps)
        out[t.key] = measure(alt) - measure(base) if reached else None
    return out
