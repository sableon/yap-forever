"""Trips away from home: rank trainers in set towns, recipe trips back to them, vendor patterns, the Favor vendor.

A trainer teaches the recipes up to its rank's cap (`recipe_rank_cap`), so every trainer visit learns the
recipes the route needs later that its rank teaches and the skill allows (`visits`); a recipe that no visit
can teach makes a visit of its own: a trip for an Artisan or Master recipe, a capital stop below. Ranks
below 225 are not trips (Expert and Journeyman trainers are in the main cities), nor AH patterns (they come
by mail). With `trainer_trips = "one_go"` the player levels at a remote rank trainer to the end of that rank's
stretch (`stretch_end`) and learns the recipes there as the skill reaches them: no visits back in between.
A rank whose trainers all stand in one capital (trainer_text.stage_capitals: `capitals`) gives its visits that
`city`; in the capital the guide starts in (`home`, plan.home_capital) they are capital stops, not trips, whatever
trainer_trips (#98), and the other capital's visits are trips that follow trainer_trips. The guide joins capital stops
of the two professions that are close together on the route into one (join_stops).
"""
import dataclasses
from dataclasses import dataclass, field

from yap_forever.gamedata import PROFESSIONS
from yap_forever.planner import measure
from yap_forever.profile import CAPITAL_NAMES
from yap_forever.trainers import RANK_BY_CAP

REMOTE_RANK = 225  # ranks to 225 (Artisan) and 300 (Master) are trained in set towns
AS_NEEDED, ONE_GO = "as_needed", "one_go"  # profile.TRAINER_TRIPS
MAX_TRIP_ALTS = 3
FREE_SKIP = 0.5  # copper: a route without a trip that costs at most this much more costs the same (plan.take_free_skips)
RANK_CAPS = tuple(sorted(RANK_BY_CAP))  # 75, 150, 225, 300: Journeyman, Expert, Artisan, Master
JOIN_SPAN = 10  # skill points: a capital stop joins an earlier one of the other profession this close (join_stops)


def recipe_rank_cap(required_skill: int) -> int:
    """The cap of the lowest trainer rank that teaches a recipe: the lowest rank cap at or above its required
    skill (75, 150, 225 or 300). A trainer teaches every recipe from 1 up to its own cap, lower ranks' included
    (confirmed in game, 2026-11-21; Expert stops at 150); this is the one place that says so."""
    return next((c for c in RANK_CAPS if c >= required_skill), RANK_CAPS[-1])


@dataclass
class Visit:
    """A trainer visit the route makes, and the trainer recipes learned there.
    kind: "rank" (a rank training: `remote` for Artisan and Master, else a capital), "recipe" (a trip to an
    Artisan or Master trainer only to learn recipes) or "city" (the same, at an Expert or Journeyman trainer
    in a capital). rank_cap: the cap of the trainer's rank. learn: trainer recipes the route needs later
    whose required skill is reached by `skill` (learn ahead). if_missing: recipes already reachable at the
    start skill (the stock doesn't say which are known), listed at the first visit that teaches them.
    as_reached: (spell, skill) for a remote rank visit with trainer_trips "one_go": the recipes of the visits it
    replaces in its stretch, learned at this trainer at the skill the route learns them (plan.learn_log).
    city: the capital zone the trainer stands in, for a rank whose trainers all stand in one (see the module); None
    for any other, and without trainer data. joined: the later capital stops of the other profession made at this one
    (join_stops; the guide only)."""
    profession: int
    skill: int
    rank_cap: int
    remote: bool
    kind: str
    learn: list[int] = field(default_factory=list)
    if_missing: list[int] = field(default_factory=list)
    as_reached: list[tuple[int, int]] = field(default_factory=list)
    city: int | None = None
    joined: list["Visit"] = field(default_factory=list)


def at_home(v: Visit, home: int | None) -> bool:
    """Whether a visit is a stop in the capital the guide starts in (no trip, no bring list)."""
    return home is not None and v.city == home


def capital_trip(v: Visit | None, home: int | None) -> bool:
    """Whether a trip's visit goes to a capital's trainer while the guide has a home capital: the AH, mailbox and bank
    are there, so the trip has no bring list (shopping.bring_text) and says so instead (guide._trip_line)."""
    return home is not None and v is not None and v.city is not None


def start_stage(plan, profession: int, start_skills: dict[int, int]) -> int | None:
    """The rank cap of the stage `profession` starts the route in, when the route levels in it; None when the route
    doesn't raise it or trains its next rank at the start skill (Blacksmithing at 225 training Master at once)."""
    start = max(1, start_skills.get(profession, 1))
    trained = [s for p, s, _c, _f in plan.ranks if p == profession]
    if plan.final_skill.get(profession, start) <= start or (trained and min(trained) <= start):
        return None
    return recipe_rank_cap(start)


def route_capitals(stage_caps: dict[tuple[int, int], int], plan,
                   start_skills: dict[int, int]) -> dict[int, list[tuple[int, int]]]:
    """capital zone -> the (profession, rank cap) of the route's stages trained there (stage_caps:
    trainer_text.stage_capitals), in route order: a stage the route starts in (its rank already trained) comes first,
    then each rank training in the order the route trains it (plan.ranks). A start stage counts only when the route
    levels in it (start_stage)."""
    stages = [(p, cap) for p in plan.final_skill if (cap := start_stage(plan, p, start_skills)) is not None]
    stages += [(p, cap) for p, _s, cap, _fee in plan.ranks]
    out: dict[int, list[tuple[int, int]]] = {}
    for stage in stages:
        if stage in stage_caps and stage not in out.setdefault(stage_caps[stage], []):
            out[stage_caps[stage]].append(stage)
    return out


def stretch_end(plan, profession: int, skill: int) -> int:
    """Where levelling at a remote rank trainer from `skill` ends with trainer_trips "one_go": the profession's next
    rank training (a trip of its own), else the end of its route (the target, or the next rank's cap)."""
    later = [s for p, s, _c, _f in plan.ranks if p == profession and s > skill]
    return min(later) if later else plan.final_skill.get(profession, skill)


PATTERN_HOWS = ("ah", "vendor", "favor", "owned", "mail")  # plan.learn_log: patterns, items the player carries


def stretch_patterns(plan, gd, profession: int, lo: int, hi: int | None = None) -> list[tuple[int, int, str]]:
    """(skill, spell, how) of the patterns `profession` learns in the one-go stretch from a remote rank training at `lo`
    to `hi` (default: stretch_end; a bring list cut shorter gives its own end), from plan.learn_log: bought on the
    AH, from a vendor or with Merchant's Favor, kept in your bank or mailed by another of your characters. A trip's
    bring list carries them, and a vendor or Favor pattern among them is no trip of its own (see trips).
    The stretch takes lo <= skill < hi: a pattern learned at the next rank training belongs to that trip's stretch.
    When no rank training comes after `lo` and `hi` is the end of the route, `hi` is in it too: the goal recipe is
    learned and crafted once at the final skill (planner._craft_once_step)."""
    end = stretch_end(plan, profession, lo) if hi is None else hi
    last = (end >= plan.final_skill.get(profession, end)
            and not any(p == profession and s > lo for p, s, _c, _f in plan.ranks))
    return [(s, spell, how) for prof, s, spell, how in plan.learn_log
            if prof == profession and lo <= s and (s < end or (last and s == end)) and how in PATTERN_HOWS
            and spell in gd.recipes and gd.recipes[spell].scroll_item]


def _one_go(out: list[Visit], plan, home: int | None = None) -> list[Visit]:
    """The visits with every visit back for recipes (a trip, or a capital stop) inside a remote rank visit's stretch
    folded into that rank visit: its recipes go to `as_reached` with the skill the route learns them at (learn_log),
    and those it was to check go to `if_missing`. A stop in the home capital (at_home) is never folded, nor folds
    others: the player is levelling there."""
    learned_at = {spell: s for _prof, s, spell, how in plan.learn_log if how == "trainer"}
    kept = []
    homes: dict[int, Visit] = {}  # profession -> its latest remote rank visit (the one later visits fold into)
    for v in out:
        if at_home(v, home):
            if v.kind == "rank":
                homes.pop(v.profession, None)
            kept.append(v)
            continue
        if v.kind == "rank":
            if v.remote:
                homes[v.profession] = v
            else:
                homes.pop(v.profession, None)
        into = homes.get(v.profession)
        if (into is not None and v.kind != "rank"
                and into.skill <= v.skill <= stretch_end(plan, into.profession, into.skill)
                and v.rank_cap <= into.rank_cap):
            into.as_reached += [(spell, learned_at.get(spell, v.skill)) for spell in v.learn]
            into.if_missing += v.if_missing
            continue
        kept.append(v)
    return kept


def _visits(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED, capitals: dict | None = None,
            home: int | None = None) -> tuple[list[Visit], dict[int, list[int]]]:
    """(visits in skill order, profession -> recipes to know before the first visit that teaches them)."""
    capitals = capitals or {}
    ranks = [Visit(prof, s, cap, cap >= REMOTE_RANK, "rank", city=capitals.get((prof, cap)))
             for prof, s, cap, _fee in plan.ranks]
    out = sorted(ranks, key=lambda v: v.skill)
    learns = sorted(((prof, s, spell, gd.recipes[spell].required_skill) for prof, s, spell, how in plan.learn_log
                     if how == "trainer" and spell in gd.recipes), key=lambda x: x[1])
    known: list[tuple[int, int, int, int]] = []

    def first(prof, req, rank, at):
        return next((v for v in out if v.profession == prof and req <= v.skill <= at and v.rank_cap >= rank), None)

    for prof, s, spell, req in learns:
        if req <= max(1, start_skills.get(prof, 1)):  # reachable at the start: never a visit of its own
            known.append((prof, s, spell, req))
            continue
        rank = recipe_rank_cap(req)
        v = first(prof, req, rank, s)
        if v is None:
            v = Visit(prof, s, rank, rank >= REMOTE_RANK, "recipe" if rank >= REMOTE_RANK else "city",
                      city=capitals.get((prof, rank)))
            out.append(v)
            out.sort(key=lambda v: v.skill)  # stable: a visit made at a rank training's skill comes after it
        v.learn.append(spell)
    before: dict[int, list[int]] = {}
    for prof, s, spell, req in known:
        rank = recipe_rank_cap(req)
        v = first(prof, req, rank, s)
        if v is None:
            before.setdefault(prof, []).append(spell)
        else:
            v.if_missing.append(spell)
    return (_one_go(out, plan, home) if trainer_trips == ONE_GO else out), before


def visits(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED, capitals: dict | None = None,
           home: int | None = None) -> list[Visit]:
    """The trainer visits of the route, in skill order: each rank training, and a visit for each trainer
    recipe that no earlier visit can teach (see Visit). start_skills: profession -> the route's start skill.
    trainer_trips: "as_needed", or "one_go" (no visits back inside a remote rank's stretch: see _one_go).
    capitals: (profession, rank cap) -> capital zone (trainer_text.stage_capitals), for Visit.city; home: the capital
    the guide starts in (plan.home_capital), whose stops one go never folds. None for either: as without trainer data."""
    return _visits(plan, gd, start_skills, trainer_trips, capitals, home)[0]


def before_start(plan, gd, start_skills: dict[int, int]) -> dict[int, list[int]]:
    """profession -> trainer recipes already reachable at the start skill that the route uses before any
    visit that teaches them: the player should know them before starting."""
    return _visits(plan, gd, start_skills)[1]


def step_place(plan, v: Visit) -> int:
    """Where a visit comes in route order: the index in plan.steps of its profession's first levelling step from its
    skill on (len(plan.steps) after the last)."""
    return next((j for j, st in enumerate(plan.steps)
                 if st.profession == v.profession and st.skill_from < st.skill_to and st.skill_from >= v.skill),
                len(plan.steps))


def skill_at(plan, profession: int, place: int) -> int:
    """A profession's skill at index `place` of plan.steps: where its next levelling step starts, else its final
    skill."""
    return next((st.skill_from for st in plan.steps[place:] if st.profession == profession and st.skill_from < st.skill_to),
                plan.final_skill.get(profession, 0))


def capital_stop(v: Visit, home: int | None) -> bool:
    """Whether the guide shows a visit as a stop in a capital, not a trip: a rank below Artisan, or a visit to the home
    capital's stage trainer (at_home)."""
    return not v.remote or at_home(v, home)


def join_city(v: Visit, home: int | None, has_trainer) -> int | None:
    """The capital a stop and the stops joined to it (Visit.joined) are made in: the home capital when it has the
    trainers of them all, else (no home) the first capital in profile.CAPITAL_NAMES order that has them; None when none
    has. has_trainer(zone, profession, rank cap): trainer_text.has_trainer with the trainer info bound."""
    zones = [home] if home is not None else list(CAPITAL_NAMES.values())
    return next((z for z in zones if all(has_trainer(z, x.profession, x.rank_cap) for x in [v, *v.joined])), None)


def join_stops(found: list[Visit], plan, gd, home: int | None, has_trainer) -> list[Visit]:
    """The visits (visits) with each capital stop B that an earlier capital stop A can take moved into A.joined, for the
    guide's rows (#98). In route order (step_place), B joins A when B is of the other profession (learn-ahead already
    teaches a profession's learnable recipes at its own stop), the city has the trainers of both (join_city: the home
    capital, or with no home any capital with both), B's profession's skill where A is made is at least B's skill less
    JOIN_SPAN, and every recipe of B can be learned at that skill. B joins whole or not at all, and the latest such A
    takes it. A rank training never moves, but it can be A. Display only: the trips, visit_count and the bring lists
    count the visits unjoined, so the route and Part 3's free skips don't change. found is left as it was.
    has_trainer: see join_city."""
    out = [dataclasses.replace(v, joined=[]) for v in found]
    places = {id(v): step_place(plan, v) for v in out}
    heads: list[Visit] = []  # the capital stops so far that later ones can join, in route order
    gone: set[int] = set()
    for v in sorted(out, key=lambda v: places[id(v)]):
        if not capital_stop(v, home):
            continue
        a = None
        if v.kind != "rank":
            a = next((a for a in reversed(heads) if a.profession != v.profession
                      and (skill := skill_at(plan, v.profession, places[id(a)])) >= v.skill - JOIN_SPAN
                      and all(gd.recipes[s].required_skill <= skill for s in v.learn + v.if_missing)
                      and join_city(dataclasses.replace(a, joined=[*a.joined, v]), home, has_trainer) is not None),
                     None)
        if a is None:
            heads.append(v)
        else:
            a.joined.append(v)
            gone.add(id(v))
    return [v for v in out if id(v) not in gone]


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

    @property
    def recipes(self) -> frozenset[int]:
        """The recipes a route without this trip leaves out: a recipe trip's recipes, or a pattern trip's recipe."""
        return frozenset(self.spells or {self.spell})


def _recipe_trip(v: Visit, gd) -> Trip:
    """The trip of a "recipe" visit: back to its Artisan or Master trainer for its recipes, with their fees."""
    return Trip(v.skill, v.profession, "recipe", ", ".join(gd.recipes[s].name for s in v.learn), None,
                sum(gd.recipes[s].fee for s in v.learn), v.rank_cap, tuple(v.learn), v)


def trips(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED, capitals: dict | None = None,
          home: int | None = None) -> list[Trip]:
    """The trips away from home, in skill order. start_skills: profession -> the route's start skill.
    trainer_trips: see visits; with "one_go", a vendor or Favor pattern learned inside a remote rank's stretch is on that
    trip's bring list (stretch_patterns), not a trip of its own. capitals, home: see visits; a stop in the home capital
    (at_home) is no trip."""
    out = []
    found = visits(plan, gd, start_skills, trainer_trips, capitals, home)
    for v in found:
        if at_home(v, home):
            continue
        name = PROFESSIONS.get(v.profession, v.profession)
        if v.kind == "rank" and v.remote:
            fee = next(f for prof, s, cap, f in plan.ranks if (prof, s, cap) == (v.profession, v.skill, v.rank_cap))
            out.append(Trip(v.skill, v.profession, "rank", f"{name} rank to {v.rank_cap}", None, fee, v.rank_cap,
                            visit=v))
        elif v.kind == "recipe":
            out.append(_recipe_trip(v, gd))
    out += _pattern_trips(plan, gd, found, trainer_trips)
    return sorted(out, key=lambda t: (t.skill, t.kind != "vendor" and t.kind != "favor", t.profession))


def _pattern_trips(plan, gd, found: list[Visit], trainer_trips: str) -> list[Trip]:
    """The vendor and Favor trips of a route whose trainer visits are `found` (visits): with "one_go", a pattern
    learned inside a remote rank's stretch is on that trip's bring list instead (stretch_patterns). A rank visit in a
    capital (Visit.city) has no bring list, so its stretch's patterns stay trips."""
    carried = {(v.profession, s, spell) for v in found
               if trainer_trips == ONE_GO and v.kind == "rank" and v.remote and v.city is None
               for s, spell, _how in stretch_patterns(plan, gd, v.profession, v.skill)}
    out = []
    for prof, s, spell, how in plan.learn_log:
        if how in ("vendor", "favor") and (prof, s, spell) not in carried:
            r = gd.recipes.get(spell)
            name = r.name if r else str(spell)
            cost = gd.vendor_prices.get(r.scroll_item, 0) if r and how == "vendor" and r.scroll_item else 0
            out.append(Trip(s, prof, how, name, spell, cost))
    return out


def visit_count(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED, capitals: dict | None = None,
                home: int | None = None) -> int:
    """What the route asks of trainers and pattern sellers: its trainer visits (visits: rank trainings, trips back
    for recipes, capital stops, the home capital's included) and its vendor and Favor trips. A free skip makes fewer
    of them. capitals, home: see visits."""
    found = visits(plan, gd, start_skills, trainer_trips, capitals, home)
    return len(found) + len(_pattern_trips(plan, gd, found, trainer_trips))


def skippable(plan, gd, start_skills: dict[int, int], trainer_trips: str = AS_NEEDED, capitals: dict | None = None,
              home: int | None = None) -> list[Trip]:
    """The trips a route could be planned without: a trip for each "recipe" visit (visits; a stop in the home capital
    too, keyed by its recipes as the trip it was) and the vendor and Favor trips (trips), in skill order."""
    found = visits(plan, gd, start_skills, trainer_trips, capitals, home)
    out = [_recipe_trip(v, gd) for v in found if v.kind == "recipe"] + _pattern_trips(plan, gd, found, trainer_trips)
    return sorted(out, key=lambda t: (t.skill, t.kind == "recipe", t.profession))


def alternatives(base, inputs, mode, cache: dict | None = None, trainer_trips: str = AS_NEEDED,
                 excluded: frozenset[int] = frozenset(), capitals: dict | None = None,
                 home: int | None = None) -> list[tuple[Trip, object, float | None]]:
    """(trip, the route planned without its recipes, what that costs more in the route's measure) for the trips
    trip_alternatives measures; (trip, None, None) when the targets can't be reached without them, and for a
    trip for the goal recipe. excluded: recipes the base route was already planned without (plan.take_free_skips),
    left out of every route planned here too. capitals, home: see visits (they never change a route planned here).
    See trip_alternatives for the rest."""
    from yap_forever.plan import plan_route  # plan imports this module

    cost = measure(mode)
    goals = set(inputs.craft_once.values())  # the goal recipe can't be skipped
    found = skippable(base, inputs.gd, inputs.stock.skills, trainer_trips, capitals, home)
    out: list[tuple[Trip, object, float | None]] = [(t, None, None) for t in found if goals & set(t.spells)]
    goal_trips = {t.key for t, _alt, _diff in out}
    patterns = sorted((t for t in found if t.spell is not None and t.spell not in goals), key=lambda t: -t.cost)
    recipes = sorted((t for t in found if t.kind == "recipe" and t.key not in goal_trips), key=lambda t: -t.cost)
    cache = {} if cache is None else cache
    for t in patterns[:MAX_TRIP_ALTS] + recipes[:MAX_TRIP_ALTS]:
        left = frozenset(excluded) | t.recipes
        k = (mode, tuple(sorted(inputs.caps.items())), left)
        if k not in cache:
            cache[k] = plan_route(inputs, mode, exclude=left)
        alt = cache[k]
        reached = all(alt.final_skill.get(p, 0) >= base.final_skill.get(p, 0) for p in inputs.caps)
        out.append((t, alt, cost(alt) - cost(base)) if reached else (t, None, None))
    return out


def trip_alternatives(base, inputs, mode, cache: dict | None = None, trainer_trips: str = AS_NEEDED,
                      excluded: frozenset[int] = frozenset(), capitals: dict | None = None,
                      home: int | None = None) -> dict[int | tuple[int, ...], float | None]:
    """What the route costs more without a trip's recipes, in the route's own measure, by Trip.key; None when
    the targets can't be reached without them. For the costliest MAX_TRIP_ALTS vendor trips (by pattern
    price; a Favor trip is always a target's, never measured), and apart from them the costliest
    MAX_TRIP_ALTS recipe trips (by their fees); a recipe trip for the goal recipe is always None.
    inputs: the plan.PlanInputs the route was planned from. cache: routes planned without some recipes, kept
    by the caller across calls (by mode, targets and the recipes left out), so none is planned twice.
    trainer_trips: see visits; a "one_go" route has no recipe trips inside a remote rank's stretch to skip.
    excluded: the recipes the route was planned without (free skips): every route planned here leaves them out too.
    capitals, home: see visits; a stop in the home capital is keyed and measured as the trip it was."""
    return {t.key: diff for t, _alt, diff in alternatives(base, inputs, mode, cache, trainer_trips, excluded, capitals,
                                                          home)}
