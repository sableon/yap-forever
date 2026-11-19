"""Plan a character's professions: the least-gold and least-total-value routes, guides and reports."""
from datetime import date
from pathlib import Path

from yap_forever import gamedata
from yap_forever.compare import ROUTE_NAMES, compare, settle_routes
from yap_forever.config import load_stock
from yap_forever.costmodel import Valuer
from yap_forever.favor import load_favor
from yap_forever.guide import render_guide
from yap_forever.planner import DISENCHANT, plan, resolve_goals
from yap_forever.prices import Market
from yap_forever.quests import load_quest_plans
from yap_forever.report import render, verdict
from yap_forever.settings import Paths
from yap_forever.shopping import render_shopping
from yap_forever.trips import trip_alternatives

REUSE_ROUNDS = 4


def unit_value(item: int, gd, market) -> float:
    """What a reagent the route makes is worth: the lowest of its AH price, vendor price and the
    cost of its own reagents."""
    opts = [x for x in (market.min_price(item), gd.vendor_prices.get(item)) if x]
    for r in gd.recipes.values():
        if r.output and r.output[0] == item:
            parts = [market.min_price(i) or gd.vendor_prices.get(i) for i in r.reagents]
            if all(parts):
                opts.append(sum(p * q for p, q in zip(parts, r.reagents.values())) / r.output[1])
    return min(opts) if opts else 0


def _rounds(gd, market, stock, favor, caps, craft_once, mode, quests, exclude, one_time_in_full,
            overtime=0, reading="relative"):
    """Plans of each reuse round: reagents later steps consume count as savings when a step makes
    them, replanned until those counts settle."""
    valuer = Valuer(market, gd, stock, mode=mode)
    makes = {r.output[0] for r in gd.recipes.values() if r.skill_line in caps and r.output}
    reuse: dict = {}
    out = []
    for _ in range(REUSE_ROUNDS):
        p = plan(gd, valuer, stock, favor, quests=quests, reuse=reuse, caps=caps,
                 craft_once=craft_once, exclude=exclude, one_time_in_full=one_time_in_full,
                 overtime=overtime, reading=reading)
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


def plan_route(gd, market, stock, favor, caps, craft_once, mode, quests, exclude=frozenset(),
               one_time_in_full=False, overtime=0, reading="relative"):
    """The best reuse round of one mode, by that mode's own measure."""
    rounds = _rounds(gd, market, stock, favor, caps, craft_once, mode, quests, exclude, one_time_in_full,
                     overtime, reading)
    routes, _ = settle_routes(rounds, caps)
    return routes[mode]


def candidates(gd, market, stock, favor, caps, craft_once, quests, overtime=0, reading="relative") -> list:
    """Every reuse round of the value mode, the gold mode, and the gold mode with one-time costs
    charged in full."""
    out = []
    for mode, full in (("value", False), ("gold", False), ("gold", True)):
        out += _rounds(gd, market, stock, favor, caps, craft_once, mode, quests, frozenset(), full, overtime, reading)
    return out


def write_reports(paths: Paths, stock_path: Path, standing: str, goals: dict, character=None,
                  reading: str = "relative") -> tuple[str, dict[str, Path]]:
    """Plan both routes from the player's prices and stock; return (comparison, written files).
    character: the profile.Character, for its talents; reading: how Working Overtime applies."""
    overtime = character.working_overtime if character else 0
    gamedata.fetch_all(dest=paths.gamedata)
    gd = gamedata.load_gamedata(paths.gamedata, professions=goals)
    stock = load_stock(stock_path)
    favor = load_favor(standing)
    quests = load_quest_plans()
    caps, once = resolve_goals(goals, gd, favor, quests)
    market = Market.load(paths.prices)
    routes, same = settle_routes(candidates(gd, market, stock, favor, caps, once, quests, overtime, reading), caps)
    trips = {m: render_shopping(r, gd, market, stock)[1] for m, r in routes.items()} if stock.bag_slots else None
    table = compare(routes, gd, market, stock, mailbox_trips=trips, same=same)
    today = date.today().isoformat()
    paths.reports.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for m, route in routes.items():
        alts = trip_alternatives(route, gd, market, stock, favor, caps, once, m, quests, overtime, reading)
        full = paths.reports / f"{today}-plan-{m}.md"
        full.write_text(render(route, verdict(route, stock, caps), market, gd, stock, favor, caps), encoding="utf-8")
        guide = paths.reports / f"{today}-guide-{m}.md"
        guide.write_text(render_guide(route, gd, market, stock, caps, ROUTE_NAMES[m].lower(), table, alts),
                         encoding="utf-8")
        files[f"plan-{m}"], files[f"guide-{m}"] = full, guide
    return table, files
