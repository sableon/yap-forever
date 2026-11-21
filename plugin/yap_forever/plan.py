"""Plan a character's professions: the least-gold and least-total-value routes, guides and reports."""
import dataclasses
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from yap_forever import budget as budget_cut
from yap_forever import favor_suggest, gamedata, trainer_text
from yap_forever.compare import ROUTE_NAMES, compare, reaches, settle_routes
from yap_forever.config import Stock, load_stock
from yap_forever.costmodel import Valuer
from yap_forever.favor import FavorData, load_favor, no_favor
from yap_forever.guide import free_skip_line, gold, render_guide
from yap_forever.planner import DISENCHANT, measure, plan, resolve_goals
from yap_forever.prices import Market
from yap_forever.profile import CAPITAL_NAMES, report_name
from yap_forever.quests import QuestPlan, load_quest_plans
from yap_forever.report import render, verdict
from yap_forever.settings import Paths
from yap_forever.shopping import render_shopping
from yap_forever.trips import (AS_NEEDED, FREE_SKIP, MAX_TRIP_ALTS, Trip, alternatives, route_capitals,
                               trip_alternatives, visit_count)

REUSE_ROUNDS = 4
MIN_SAVING = 100  # copper: below 1 silver the gap is noise from the greedy planner, not a saving to name


@dataclass(frozen=True, kw_only=True)
class PlanInputs:
    """What every planning round of one character reads: game data, prices, stock, Favor, the targets
    (caps: profession -> skill; craft_once: profession -> recipe crafted once at the end), the quest
    recipes, and the character's Working Overtime rank and how it reads (see costmodel.skillup_chance);
    order: raise the professions one at a time in this order (None: side by side; see planner.plan)."""
    gd: gamedata.GameData
    market: Market
    stock: Stock
    favor: FavorData
    caps: dict[int, int]
    craft_once: dict[int, int]
    quests: dict[int, QuestPlan]
    overtime: int = 0
    reading: str = "relative"
    order: tuple[int, ...] | None = None


def home_capital(stage_caps: dict[tuple[int, int], int], plan, character,
                 start_skills: dict[int, int] | None = None) -> int | None:
    """The capital zone the guide starts in and levels its stages in (#98): the character's `capital`, else the only
    capital the route's stages need, else the one whose stage the route reaches first (trips.route_capitals).
    None without stage capitals (no trainer data or faction, RF2) or when the route has no stage in a capital, the key
    set or not."""
    needed = route_capitals(stage_caps or {}, plan, start_skills or {})
    if not needed:
        return None
    if character is not None and character.capital:
        return CAPITAL_NAMES[character.capital]
    return next(iter(needed))


def unit_value(item: int, gd, market) -> float:
    """What a reagent the route makes is worth: the lowest of its AH price, vendor price and the
    cost of its own reagents."""
    opts = [x for x in (market.min_price(item), gd.vendor_prices.get(item)) if x]
    for r in gd.recipes.values():
        if r.output and r.output[0] == item:
            parts = [market.min_price(i) or gd.vendor_prices.get(i) for i in r.reagents]
            if all(parts):
                opts.append(sum(p * q for p, q in zip(parts, r.reagents.values(), strict=True)) / r.output[1])
    return min(opts) if opts else 0


def _rounds(inputs: PlanInputs, mode, exclude, one_time_in_full, vendor_credit=True):
    """Plans of each reuse round: reagents later steps consume count as savings when a step makes
    them, replanned until those counts settle. vendor_credit: see planner.plan."""
    gd, market = inputs.gd, inputs.market
    valuer = Valuer(market, gd, inputs.stock, mode=mode)
    makes = {r.output[0] for r in gd.recipes.values() if r.skill_line in inputs.caps and r.output}
    reuse: dict = {}
    out = []
    for _ in range(REUSE_ROUNDS):
        p = plan(gd, valuer, inputs.stock, inputs.favor, quests=inputs.quests, reuse=reuse, caps=inputs.caps,
                 craft_once=inputs.craft_once, exclude=exclude, one_time_in_full=one_time_in_full,
                 overtime=inputs.overtime, reading=inputs.reading, order=inputs.order, vendor_credit=vendor_credit)
        out.append(p)
        used: dict[int, float] = {}
        for st in p.steps:
            r = gd.recipes.get(st.spell_id) if st.spell_id != DISENCHANT else None
            for i, q in (r.reagents.items() if r else ()):
                if i in makes:
                    used[i] = used.get(i, 0) + q * st.crafts
        if not used and not reuse:
            break
        if reuse and all(abs(used.get(i, 0) - reuse.get(i, (0,))[0]) < 1 for i in set(used) | set(reuse)):
            break
        reuse = {i: (n, unit_value(i, gd, market)) for i, n in used.items()}
    return out


def plan_route(inputs: PlanInputs, mode, exclude=frozenset(), one_time_in_full=False, vendor_credit=True):
    """The best reuse round of one mode, by that mode's own measure. vendor_credit: see planner.plan."""
    rounds = _rounds(inputs, mode, exclude, one_time_in_full, vendor_credit)
    routes, _ = settle_routes(rounds, inputs.caps)
    return routes[mode]


def candidates(inputs: PlanInputs, vendor_credit: bool = True) -> list:
    """Every reuse round of the value mode, the gold mode, and the gold mode with one-time costs
    charged in full. vendor_credit False: a budget's fallback (budget.cut), every reuse round of the value mode and
    the gold mode planned without the vendor price of the crafts sold in the score (planner.plan)."""
    out = []
    families = (("value", False), ("gold", False), ("gold", True)) if vendor_credit else (("value", False),
                                                                                          ("gold", False))
    for mode, full in families:
        out += _rounds(inputs, mode, frozenset(), full, vendor_credit)
    return out


def listed_savings(inputs: PlanInputs, routes) -> dict[str, float]:
    """What the routes could cost less if every trainer offered its recipes at the Forever listing:
    mode -> copper, in the mode's own measure, for the modes where it is worth saying.
    inputs.gd: the game data the routes were planned on (see gamedata.safe_requirements); routes: their
    settled routes. The listed routes are settled the same way, from the same candidates, planned with the same
    vendor credit as the route (Plan.vendor_credit)."""
    gd, caps = inputs.gd, inputs.caps
    if not any(r.listed_skill is not None for r in gd.recipes.values()):
        return {}
    at_listing = dataclasses.replace(inputs, gd=gamedata.listed_requirements(gd))
    settled: dict[bool, dict] = {}  # vendor credit -> the listed routes
    out = {}
    for mode, safe in routes.items():
        credit = safe.vendor_credit
        if credit not in settled:
            settled[credit] = settle_routes(candidates(at_listing, vendor_credit=credit), caps)[0]
        listed = settled[credit]
        cost = measure(mode)
        saving = cost(safe) - cost(listed[mode])
        if saving >= MIN_SAVING and (reaches(listed[mode], caps) or not reaches(safe, caps)):
            out[mode] = saving
    return out


def take_free_skips(route, inputs: PlanInputs, mode, cache: dict, trainer_trips: str = AS_NEEDED, fits=None,
                    excluded: frozenset[int] = frozenset(), also: tuple[str, ...] = (), capitals: dict | None = None,
                    home: int | None = None) -> tuple:
    """(the route planned without the trips that cost nothing to skip, those trips in the order left out).

    Round by round, at most MAX_TRIP_ALTS rounds, among the trips trip_alternatives measures, a trip is left out
    when the route without it:
    - costs at most FREE_SKIP more (or less) than the round's route and than `route` as given (the route as first
      settled, so the rounds together stay within FREE_SKIP), in the route's measure and in that of each mode in
      `also` (the other mode of a route the gold and value guides share);
    - reaches every profession's final skill;
    - makes fewer trainer visits and pattern trips than the round's route (trips.visit_count);
    - and, when fits is given (a budget: its gold to bring within the budget), fits.
    The cheapest such route is taken (on a tie the first in trip_alternatives' order: pattern trips, then recipe
    trips, each costliest first), and the next round plans without its recipes too. The goal recipe is never left
    out. cache, trainer_trips: as for trip_alternatives; excluded: recipes `route` was planned without. capitals, home:
    see trips.visits; a stop in the home capital is a candidate like the trip it was, and every route is counted with
    the same home."""
    left: list[Trip] = []
    excluded = frozenset(excluded)
    gd, start = inputs.gd, inputs.stock.skills
    original = route
    costs = [measure(m) for m in (mode, *also)]

    def free(alt, now):  # within FREE_SKIP of the original and of the round's route, in every measure
        return all(c(alt) - c(base) <= FREE_SKIP for c in costs for base in (original, now))
    for _ in range(MAX_TRIP_ALTS):
        visits_now = visit_count(route, gd, start, trainer_trips, capitals, home)
        found = [(costs[0](alt), t, alt) for t, alt, diff in alternatives(route, inputs, mode, cache, trainer_trips,
                                                                         excluded, capitals, home)
                 if diff is not None and free(alt, route)
                 and visit_count(alt, gd, start, trainer_trips, capitals, home) < visits_now
                 and (fits is None or fits(alt))]
        if not found:
            break
        _cost, t, route = min(found, key=lambda x: x[0])
        excluded |= t.recipes
        left.append(t)
    return route, left


def _free_skips(routes: dict, per_mode: dict, cache: dict, trainer_trips: str, limit: int | None,
                gold_of, capitals: dict | None = None, homes: dict | None = None) -> dict[str, tuple]:
    """mode -> take_free_skips of its route (with a budget, a route-without must bring at most `limit` copper,
    by gold_of). Gold and value on one route to the same caps are adopted once, free in both measures, so they stay
    one route. capitals, homes: trips.visits' capitals, and mode -> its route's home capital."""
    shared = routes["gold"] is routes["value"] and per_mode["gold"].caps == per_mode["value"].caps
    out: dict[str, tuple] = {}
    for m, route in routes.items():
        if m == "value" and shared:
            out[m] = out["gold"]
            continue
        fits = None if limit is None else (lambda p: gold_of(p) <= limit)
        out[m] = take_free_skips(route, per_mode[m], m, cache, trainer_trips=trainer_trips, fits=fits,
                                 also=("value",) if shared else (), capitals=capitals,
                                 home=(homes or {}).get(m))
    return out


def saving_line(copper: float) -> str:
    return (f"A route planned at the Forever listing (trainers offering recipes from their listed skill) "
            f"could cost about {gold(copper)} less.")


def budget_dropped(goals: dict, target) -> str:
    """The line the plan command prints when write_reports won't apply `target` (a config.Budget or None) because a
    goal is a recipe (config.Goal.recipe), or ""."""
    if target is None or all(g.recipe is None for g in goals.values()):
        return ""
    return budget_cut.not_applied(target)


def write_reports(paths: Paths, stock_path: Path, standing: str, goals: dict, character=None,
                  reading: str = "relative", faction: str = "",
                  profile_names=(), study_hint_gold_per_point: float = 100,
                  group=None, target=None) -> tuple[str, dict[str, Path]]:
    """Plan both routes from the player's prices and stock; return (comparison, written files).
    character: the profile.Character, for its talents and trainer_trips; reading: how Working Overtime applies.
    faction ("alliance" or "horde"): name rank trainers for it in the guide; "" names none. Horde gets no
    Merchant's Favor recipes or crate turn-ins (see favor.no_favor).
    study_hint_gold_per_point: a route row of the lowest profession that costs this much gold a point
    gets a Dedicated Study hint (profile.toml, default 100).
    group: the shared.Group of the character: the mailable items of its other characters join the plan, and
    the report's budget line is the group's shared gold (without it, the stock's own `cash_gold`).
    target: a config.Budget to plan to (each route cut at the last stop it reaches; see budget.cut), or None. With a
    recipe goal it is not applied (every target planned in full) and the guide and the report say so
    (budget_dropped); the caller prints it too.
    Trainer recipes are planned at their inferred requirement, the safe one (gamedata.safe_requirements).
    The files are named for the character (see profile.report_name; profile_names: every character in the
    profile); without a character they keep the plain names."""
    overtime = character.working_overtime if character else 0
    gamedata.fetch_all(dest=paths.gamedata, skip=gamedata.TRAINER_FILES)
    gamedata.prune_stale(paths.gamedata)  # copies of earlier pins; never stops the plan
    trainer_info, trainer_note = trainer_text.load_info(paths.gamedata, faction)
    quests = load_quest_plans()
    gd = gamedata.safe_requirements(gamedata.load_gamedata(paths.gamedata, professions=goals), skip=quests)
    stock = load_stock(stock_path)
    budget = None
    if group is not None:
        stock.shared = group.shared_items(gd)
        budget = group.budget(stock)
    favor = no_favor() if faction == "horde" else load_favor(standing)  # the Favor list is Alliance's
    caps, once = resolve_goals(goals, gd, favor, quests)
    market = Market.load(paths.prices)
    dropped = []
    if line := budget_dropped(goals, target):  # a recipe goal wins over a budget: planned in full, and said
        target, dropped = None, [line]
    inputs = PlanInputs(gd=gd, market=market, stock=stock, favor=favor, caps=caps, craft_once=once,
                        quests=quests, overtime=overtime, reading=reading, order=target.order if target else None)
    routes, same = settle_routes(candidates(inputs), caps)
    per_mode = {m: inputs for m in routes}  # each route's own targets: a budget cuts each at its own stops
    cuts: dict[str, budget_cut.BudgetCut] = {}

    gold_of = budget_cut.gold_measure(target, gd, market, stock)  # the cut, its free skips and its spent alike
    if target is not None:
        cache = {budget_cut.key(caps): (routes, same, None)}  # the routes without vendor credit: planned if needed
        cuts = {m: budget_cut.cut(inputs, m, target, gold_of, cache) for m in routes}
        routes = {m: c.plan for m, c in cuts.items()}
        per_mode = {m: dataclasses.replace(inputs, caps=c.planned_caps) for m, c in cuts.items()}
    trainer_trips = character.trainer_trips if character else "as_needed"
    # #98: where each route's stages are levelled (its home capital), fixed before free skips so every route a skip
    # compares is counted with the same home; without trainer data or a faction, none (RF2)
    capitals = trainer_text.stage_capitals(trainer_info)
    homes = {m: home_capital(capitals, r, character, stock.skills) for m, r in routes.items()}
    needed = {m: route_capitals(capitals, r, stock.skills) for m, r in routes.items()}  # what each home came from
    alt_cache: dict = {}
    left_out = _free_skips(routes, per_mode, alt_cache, trainer_trips,
                           None if target is None else budget_cut.copper(target), gold_of, capitals, homes)
    adopted: dict[int, object] = {}  # id of a route taken -> the plan its cut holds (one for a route both share)
    for m, (route, _left) in left_out.items():
        if m in cuts and route is not cuts[m].plan:
            cuts[m] = budget_cut.adopt(cuts[m], adopted.get(id(route), route), gold_of(route))
            adopted[id(route)] = cuts[m].plan
            route = cuts[m].plan
        routes[m] = route
    same = routes["gold"] is routes["value"]
    trips = {m: render_shopping(r, gd, market, stock)[1] for m, r in routes.items()} if stock.bag_slots else None
    # Favor recipes to craft once, apart from the route: the group's gold before the route, and the group's mail
    found = favor_suggest.suggest(gd, favor, stock, Valuer(market, gd, stock),
                                  budget.copper if budget is not None else stock.cash,
                                  stock.shared, set(once.values()))
    could_guide = favor_suggest.lines(found, gd, stock.favor, limit=favor_suggest.GUIDE_LIMIT)  # the report: all
    could_report = favor_suggest.lines(found, gd, stock.favor, heading="**You could also make**")
    level_note = [favor_suggest.NO_LEVEL_NOTE] if favor.recipes and not stock.level_set else []
    if cuts:  # once per set of caps the cuts landed on
        savings = {}
        for k in {budget_cut.key(c.planned_caps) for c in cuts.values()}:
            modes = [m for m, c in cuts.items() if budget_cut.key(c.planned_caps) == k]
            savings.update(listed_savings(per_mode[modes[0]], {m: routes[m] for m in modes}))
    else:
        savings = listed_savings(inputs, routes)
    table = compare(routes, gd, market, stock, mailbox_trips=trips, same=same, trainer_trips=trainer_trips,
                    capitals=capitals, homes=homes)
    today = date.today().isoformat()
    paths.reports.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    who = f"{report_name(character.name, profile_names)}-" if character else ""
    alts_of: dict[str, dict] = {}
    for m, route in routes.items():
        caps = per_mode[m].caps
        left = left_out[m][1]
        if m == "value" and route is routes.get("gold") and caps == per_mode["gold"].caps:
            alts = alts_of["gold"]  # the same route: its trips are skipped at the same cost
        else:
            alts = trip_alternatives(route, per_mode[m], m, alt_cache, trainer_trips=trainer_trips,
                                     excluded=frozenset().union(*(t.recipes for t in left)), capitals=capitals,
                                     home=homes[m])
        alts_of[m] = alts
        skips = [free_skip_line(t, gd, trainer_info, homes[m]) for t in left]
        full = paths.reports / f"{today}-{who}plan-{m}.md"
        line = saving_line(savings[m]) if m in savings else ""
        said = budget_cut.lines(cuts[m], target) if m in cuts else dropped
        empty = m in cuts and cuts[m].below_first_stop
        full.write_text(render(route, verdict(route, stock), market, gd, stock, favor, caps,
                               character, reading, saving_line=line, budget=budget,
                               notes=[*(group.notes() if group else ()), *level_note], budget_lines=said, goal=target,
                               nothing_in_budget=empty, free_skips=skips, could_make=could_report),
                        encoding="utf-8")
        guide = paths.reports / f"{today}-{who}guide-{m}.md"
        guide.write_text(render_guide(route, gd, market, stock, caps, ROUTE_NAMES[m].lower(), table, alts,
                                       character=character, reading=reading,
                                       trainer_info=trainer_info, trainer_note=trainer_note,
                                       saving_line=line, mode=m,
                                       study_hint_gold_per_point=study_hint_gold_per_point,
                                       budget_lines=said, order=inputs.order, nothing_in_budget=empty,
                                       trainer_trips=trainer_trips, free_skips=skips, could_make=could_guide,
                                       capitals=capitals, home=homes[m], capital_stages=needed[m],
                                       extra_notes=[*(group.notes() if group else ()), *([favor.note] if favor.note else []),
                                                    *level_note]),
                         encoding="utf-8")
        files[f"plan-{m}"], files[f"guide-{m}"] = full, guide
    return table, files
