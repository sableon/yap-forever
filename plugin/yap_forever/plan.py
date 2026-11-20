"""Plan a character's professions: the least-gold and least-total-value routes, guides and reports."""
import dataclasses
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from yap_forever import gamedata, trainer_text
from yap_forever.compare import ROUTE_NAMES, compare, reaches, settle_routes
from yap_forever.config import Stock, load_stock
from yap_forever.costmodel import Valuer
from yap_forever.favor import FavorData, load_favor, no_favor
from yap_forever.guide import gold, render_guide
from yap_forever.planner import DISENCHANT, plan, resolve_goals
from yap_forever.prices import Market
from yap_forever.profile import report_name
from yap_forever.quests import QuestPlan, load_quest_plans
from yap_forever.report import render, verdict
from yap_forever.settings import Paths
from yap_forever.shopping import render_shopping
from yap_forever.trips import trip_alternatives

REUSE_ROUNDS = 4
MIN_SAVING = 100  # copper: below 1 silver the gap is noise from the greedy planner, not a saving to name


@dataclass(frozen=True, kw_only=True)
class PlanInputs:
    """What every planning round of one character reads: game data, prices, stock, Favor, the targets
    (caps: profession -> skill; craft_once: profession -> recipe crafted once at the end), the quest
    recipes, and the character's Working Overtime rank and how it reads (see costmodel.skillup_chance)."""
    gd: gamedata.GameData
    market: Market
    stock: Stock
    favor: FavorData
    caps: dict[int, int]
    craft_once: dict[int, int]
    quests: dict[int, QuestPlan]
    overtime: int = 0
    reading: str = "relative"


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


def _rounds(inputs: PlanInputs, mode, exclude, one_time_in_full):
    """Plans of each reuse round: reagents later steps consume count as savings when a step makes
    them, replanned until those counts settle."""
    gd, market = inputs.gd, inputs.market
    valuer = Valuer(market, gd, inputs.stock, mode=mode)
    makes = {r.output[0] for r in gd.recipes.values() if r.skill_line in inputs.caps and r.output}
    reuse: dict = {}
    out = []
    for _ in range(REUSE_ROUNDS):
        p = plan(gd, valuer, inputs.stock, inputs.favor, quests=inputs.quests, reuse=reuse, caps=inputs.caps,
                 craft_once=inputs.craft_once, exclude=exclude, one_time_in_full=one_time_in_full,
                 overtime=inputs.overtime, reading=inputs.reading)
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


def plan_route(inputs: PlanInputs, mode, exclude=frozenset(), one_time_in_full=False):
    """The best reuse round of one mode, by that mode's own measure."""
    rounds = _rounds(inputs, mode, exclude, one_time_in_full)
    routes, _ = settle_routes(rounds, inputs.caps)
    return routes[mode]


def candidates(inputs: PlanInputs) -> list:
    """Every reuse round of the value mode, the gold mode, and the gold mode with one-time costs
    charged in full."""
    out = []
    for mode, full in (("value", False), ("gold", False), ("gold", True)):
        out += _rounds(inputs, mode, frozenset(), full)
    return out


def listed_savings(inputs: PlanInputs, routes) -> dict[str, float]:
    """What the routes could cost less if every trainer offered its recipes at the Forever listing:
    mode -> copper, in the mode's own measure, for the modes where it is worth saying.
    inputs.gd: the game data the routes were planned on (see gamedata.safe_requirements); routes: their
    settled routes. The listed routes are settled the same way, from the same candidates."""
    gd, caps = inputs.gd, inputs.caps
    if not any(r.listed_skill is not None for r in gd.recipes.values()):
        return {}
    listed, _ = settle_routes(candidates(dataclasses.replace(inputs, gd=gamedata.listed_requirements(gd))), caps)
    out = {}
    for mode, safe in routes.items():
        better, measure = listed[mode], ("cash_total" if mode == "gold" else "economic_total")
        saving = getattr(safe, measure) - getattr(better, measure)
        if saving >= MIN_SAVING and (reaches(better, caps) or not reaches(safe, caps)):
            out[mode] = saving
    return out


def saving_line(copper: float) -> str:
    return (f"A route planned at the Forever listing (trainers offering recipes from their listed skill) "
            f"could cost about {gold(copper)} less.")


def write_reports(paths: Paths, stock_path: Path, standing: str, goals: dict, character=None,
                  reading: str = "relative", faction: str = "",
                  profile_names=(), study_hint_gold_per_point: float = 100,
                  group=None) -> tuple[str, dict[str, Path]]:
    """Plan both routes from the player's prices and stock; return (comparison, written files).
    character: the profile.Character, for its talents; reading: how Working Overtime applies.
    faction ("alliance" or "horde"): name rank trainers for it in the guide; "" names none. Horde gets no
    Merchant's Favor recipes or crate turn-ins (see favor.no_favor).
    study_hint_gold_per_point: a route row of the lowest profession that costs this much gold a point
    gets a Dedicated Study hint (profile.toml, default 100).
    group: the shared.Group of the character: the mailable items of its other characters join the plan, and
    the report's budget line is the group's shared gold (without it, the stock's own `cash_gold`).
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
    inputs = PlanInputs(gd=gd, market=market, stock=stock, favor=favor, caps=caps, craft_once=once,
                        quests=quests, overtime=overtime, reading=reading)
    routes, same = settle_routes(candidates(inputs), caps)
    trips = {m: render_shopping(r, gd, market, stock)[1] for m, r in routes.items()} if stock.bag_slots else None
    savings = listed_savings(inputs, routes)
    table = compare(routes, gd, market, stock, mailbox_trips=trips, same=same)
    today = date.today().isoformat()
    paths.reports.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    who = f"{report_name(character.name, profile_names)}-" if character else ""
    for m, route in routes.items():
        alts = trip_alternatives(route, inputs, m)
        full = paths.reports / f"{today}-{who}plan-{m}.md"
        line = saving_line(savings[m]) if m in savings else ""
        full.write_text(render(route, verdict(route, stock), market, gd, stock, favor, caps,
                               character, reading, saving_line=line, budget=budget,
                               notes=group.notes() if group else ()), encoding="utf-8")
        guide = paths.reports / f"{today}-{who}guide-{m}.md"
        guide.write_text(render_guide(route, gd, market, stock, caps, ROUTE_NAMES[m].lower(), table, alts,
                                       character=character, reading=reading,
                                       trainer_info=trainer_info, trainer_note=trainer_note,
                                       saving_line=line, mode=m,
                                       study_hint_gold_per_point=study_hint_gold_per_point,
                                       extra_notes=[*(group.notes() if group else ()), *([favor.note] if favor.note else [])]),
                         encoding="utf-8")
        files[f"plan-{m}"], files[f"guide-{m}"] = full, guide
    return table, files
