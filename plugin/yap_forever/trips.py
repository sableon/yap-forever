"""Trips away from home: rank trainers in set towns, recipe trips back to them, vendor patterns, the Favor vendor.

A trainer teaches the recipes up to its rank's cap (`recipe_rank_cap`), so every trainer visit learns the
recipes the route needs later that its rank teaches and the skill allows (`visits`); a recipe that no visit
can teach makes a visit of its own: a trip for an Artisan or Master recipe, a capital stop below. Ranks
below 225 are not trips (Expert and Journeyman trainers are in the main cities), nor AH patterns (they come
by mail). With `trainer_trips = "one_go"` the player levels at a remote rank trainer to the end of that rank's
stretch (`stretch_end`) and learns the recipes there as the skill reaches them: no visits back in between.
"""
from dataclasses import dataclass, field

from yap_forever.gamedata import PROFESSIONS
from yap_forever.trainers import RANK_BY_CAP

REMOTE_RANK = 225  # ranks to 225 (Artisan) and 300 (Master) are trained in set towns
AS_NEEDED, ONE_GO = "as_needed", "one_go"  # profile.TRAINER_TRIPS
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
    fallback: spell -> the cap of the lowest rank that teaches it, for recipes below this trainer's rank.
    as_reached: (spell, skill) for a remote rank visit with trainer_trips "one_go": the recipes of the visits it
    replaces in its stretch, learned at this trainer when the route reaches that skill."""
    profession: int
    skill: int
    rank_cap: int
    remote: bool
    kind: str
    learn: list[int] = field(default_factory=list)
    if_missing: list[int] = field(default_factory=list)
    fallback: dict[int, int] = field(default_factory=dict)
    as_reached: list[tuple[int, int]] = field(default_factory=list)


def stretch_end(plan, profession: int, skill: int) -> int:
    """Where levelling at a remote rank trainer from `skill` ends with trainer_trips "one_go": the profession's next
    rank training (a trip of its own), else the end of its route (the target, or the next rank's cap)."""
    later = [s for p, s, _c, _f in plan.ranks if p == profession and s > skill]
    return min(later) if later else plan.final_skill.get(profession, skill)


def _one_go(out: list[Visit], plan, gd) -> list[Visit]:
    """The visits with every visit back for recipes (a trip, or a capital stop) inside a remote rank visit's stretch
    folded into that rank visit: its recipes go to `as_reached`, and those it was to check go to `if_missing`."""
    kept = []
    homes: dict[int, Visit] = {}  # profession -> its latest remote rank visit
    for v in out:
        if v.kind == "rank":
            if v.remote:
                homes[v.profession] = v
            else:
                homes.pop(v.profession, None)
        home = homes.get(v.profession)
        if (home is not None and v.kind != "rank"
                and home.skill <= v.skill <= stretch_end(plan, home.profession, home.skill)
                and v.rank_cap <= home.rank_cap):
            for spell in v.learn + v.if_missing:
                rank = recipe_rank_cap(gd.recipes[spell].required_skill)
                if rank < home.rank_cap:
                    home.fallback[spell] = rank
            home.as_reached += [(spell, v.skill) for spell in v.learn]
            home.if_missing += v.if_missing
            continue
        kept.append(v)
    return kept


def _visits(plan, gd, start_skills: dict[int, int],
            trainer_trips: str = AS_NEEDED) -> tuple[list[Visit], dict[int, list[int]]]:
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
    return (_one_go(out, plan, gd) if trainer_trips == ONE_GO else out), before


def visits(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED) -> list[Visit]:
    """The trainer visits of the route, in skill order: each rank training, and a visit for each trainer
    recipe that no earlier visit can teach (see Visit). start_skills: profession -> the route's start skill.
    trainer_trips: "as_needed", or "one_go" (no visits back inside a remote rank's stretch: see _one_go)."""
    return _visits(plan, gd, start_skills, trainer_trips)[0]


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
    visit: Visit | None = field(default=None, compare=False)  # a rank or recipe trip's trainer visit

    @property
    def key(self) -> int | tuple[int, ...] | None:
        """What trip_alternatives keys the trip by: its recipe, or a recipe trip's recipes."""
        return self.spells or self.spell


def trips(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED) -> list[Trip]:
    """The trips away from home, in skill order. start_skills: profession -> the route's start skill.
    trainer_trips: see visits."""
    out = []
    for v in visits(plan, gd, start_skills, trainer_trips):
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


def trip_alternatives(base, inputs, mode, cache: dict | None = None,
                      trainer_trips: str = AS_NEEDED) -> dict[int | tuple[int, ...], float | None]:
    """What the route costs more without a trip's recipes, in the route's own measure, by Trip.key; None when
    the targets can't be reached without them. For the costliest MAX_TRIP_ALTS vendor and Favor trips (by
    pattern price), and apart from them the costliest MAX_TRIP_ALTS recipe trips (by their fees); a recipe
    trip for the goal recipe is always None.
    inputs: the plan.PlanInputs the route was planned from. cache: routes planned without some recipes, kept
    by the caller across calls (by mode, targets and the recipes left out), so none is planned twice.
    trainer_trips: see visits; a "one_go" route has no recipe trips inside a remote rank's stretch to skip."""
    from yap_forever.plan import plan_route  # plan imports this module

    measure = (lambda p: p.cash_total) if mode == "gold" else (lambda p: p.economic_total)
    goals = set(inputs.craft_once.values())  # the goal recipe can't be skipped
    found = trips(base, inputs.gd, inputs.stock.skills, trainer_trips)
    out: dict[int | tuple[int, ...], float | None] = {t.key: None for t in found if goals & set(t.spells)}
    patterns = sorted((t for t in found if t.spell is not None and t.spell not in goals), key=lambda t: -t.cost)
    recipes = sorted((t for t in found if t.kind == "recipe" and t.key not in out), key=lambda t: -t.cost)
    picks = patterns[:MAX_TRIP_ALTS] + recipes[:MAX_TRIP_ALTS]
    cache = {} if cache is None else cache
    for t in picks:
        excluded = frozenset(t.spells or {t.spell})
        k = (mode, tuple(sorted(inputs.caps.items())), excluded)
        if k not in cache:
            cache[k] = plan_route(inputs, mode, exclude=excluded)
        alt = cache[k]
        reached = all(alt.final_skill.get(p, 0) >= base.final_skill.get(p, 0) for p in inputs.caps)
        out[t.key] = measure(alt) - measure(base) if reached else None
    return out
