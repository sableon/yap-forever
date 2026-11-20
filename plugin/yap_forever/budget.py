"""A budget as a goal: each route ends at the last stop its gold reaches.

Stops are the rank caps (75, 150, 225, 300) and each profession's own target. The gold a route needs is
the shopping list's "Gold to bring" (whole crafts with the buffer, patterns and fees), so the cut route
always fits the list the player shops from.
"""
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from yap_forever.compare import settle_routes
from yap_forever.config import Budget
from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import gold
from yap_forever.planner import Plan

STOPS = (75, 150, 225, 300)
COPPER_PER_GOLD = 10000


def stops_for(start: int, target: int) -> list[int]:
    """The stops above `start` up to `target`, the target included."""
    return [s for s in STOPS if start < s < target] + ([target] if target > start else [])


@dataclass
class BudgetCut:
    """caps: the stop each profession reaches (its start skill when the budget reaches none); plan: the route
    planned to them; spent: its gold to bring (copper); next_stop: profession -> (the next stop, the extra
    copper it costs); stalled: the stall reasons of professions that can't advance, so get no gold.
    planned_caps: the caps the plan was made with (a stalled profession keeps its target, so the plan says
    why it stops); start: the skills the route starts from."""
    caps: dict[int, int]
    plan: Plan
    spent: float
    next_stop: dict[int, tuple[int, float]]
    stalled: dict[int, str]
    planned_caps: dict[int, int] = field(default_factory=dict)
    start: dict[int, int] = field(default_factory=dict)


def key(caps: dict[int, int]) -> tuple:
    """The cache key of a set of caps (see cut's `cache`)."""
    return tuple(sorted(caps.items()))


def cut(inputs, mode: str, budget: Budget, gold_of: Callable[[Plan], float], cache: dict | None = None) -> BudgetCut:
    """The `mode` route ("gold" or "value") cut at the last stops `budget` reaches.

    Stops are taken one at a time, each checked on a route planned again to it: with budget.order, the first
    profession takes its stops while the next one fits, then the second takes what is left; side by side,
    the profession with the lower stop goes first, and when its next stop doesn't fit the other one's may
    (the gold left goes to it). A stop is taken only when gold_of(route) fits the budget, so the next stop
    of each profession is the one that doesn't: its cost is that route's gold minus the cut route's.
    inputs: plan.PlanInputs with the targets as caps (a recipe goal is not cut: the caller plans it in full).
    cache: caps key -> (routes, same) from compare.settle_routes, shared by both modes' cuts (planning a
    set of caps takes seconds); give it the routes to the targets when the caller has them."""
    from yap_forever.plan import candidates  # plan imports this module
    inputs = dataclasses.replace(inputs, order=budget.order)
    cache = {} if cache is None else cache
    limit = budget.gold * COPPER_PER_GOLD
    target = dict(inputs.caps)
    start = {p: max(1, inputs.stock.skills.get(p, 1)) for p in target}

    def routes(caps):
        k = key(caps)
        if k not in cache:
            sub = dataclasses.replace(inputs, caps=dict(caps))
            cache[k] = settle_routes(candidates(sub), sub.caps)
        return cache[k][0]

    full = routes(target)[mode]
    stops, stalled = {}, {}
    for p, t in target.items():
        stops[p] = stops_for(start[p], min(t, full.final_skill.get(p, start[p])))
        if not stops[p] and start[p] < t and p in full.stall_reasons:
            stalled[p] = full.stall_reasons[p]

    def caps_at(level):
        """level: profession -> stops taken. With all of them the cap is the target, so a profession the
        route stalls keeps its stall reason."""
        return {p: target[p] if n == len(stops[p]) else stops[p][n - 1] if n else start[p]
                for p, n in level.items()}

    def plan_at(level):
        caps = caps_at(level)
        p = routes(caps)[mode]
        held = {f"{PROFESSIONS[x]} already at {start[x]}" for x in caps if caps[x] == start[x] < target[x]}
        p.events = [e for e in p.events if e not in held]  # held at the start by the budget: not a target reached
        k = ("gold", mode, key(caps))
        if k not in cache:
            cache[k] = gold_of(p)
        return p, cache[k]

    def reached(level):
        return {p: stops[p][n - 1] if n else start[p] for p, n in level.items()}

    level = {p: len(stops[p]) for p in target}
    plan, spent = plan_at(level)
    if spent <= limit:
        return BudgetCut(reached(level), plan, spent, {}, stalled, caps_at(level), start)

    level = {p: 0 for p in target}
    plan, spent = plan_at(level)

    def more(p):
        return {**level, p: level[p] + 1}

    def left(p):
        return level[p] < len(stops[p])

    order = [p for p in budget.order or () if p in target]
    if order and len(target) > 1:
        for p in order + [p for p in target if p not in order]:
            while left(p):
                trial, (tp, tg) = more(p), plan_at(more(p))
                if tg > limit:
                    break
                level, plan, spent = trial, tp, tg
    else:
        while True:
            open_ = sorted((p for p in target if left(p)), key=lambda p: (caps_at(level)[p], p))
            took = False
            for p in open_:  # the lower one first; when its stop doesn't fit, the other one's
                tp, tg = plan_at(more(p))
                if tg <= limit:
                    level, plan, spent, took = more(p), tp, tg, True
                    break
            if not took:
                break
    next_stop = {p: (stops[p][level[p]], plan_at(more(p))[1] - spent) for p in target if left(p)}
    return BudgetCut(reached(level), plan, spent, next_stop, stalled, caps_at(level), start)


def amount(budget: Budget) -> str:
    """The budget as the player gave it: '36g', '12.5g'."""
    return f"{budget.gold:.2f}".rstrip("0").rstrip(".") + "g"


def lines(c: BudgetCut, budget: Budget) -> list[str]:
    """What the budget reaches, why a profession gets none of it, and what each next stop costs on top."""
    b = amount(budget)
    moved = [p for p in c.caps if c.caps[p] > c.start.get(p, c.caps[p])]
    if moved:
        out = [f"{b} takes " + " and ".join(f"{PROFESSIONS[p]} to {c.caps[p]}" for p in moved)
               + f" ({gold(c.spent)})."]
    else:
        out = [f"{b} doesn't reach the first stop: nothing is planned yet."]
    for p, why in c.stalled.items():
        name = PROFESSIONS[p]
        out.append(f"{name} gets none of it: {why.removeprefix(name + ': ')}.")
    out += [f"The next stop, {PROFESSIONS[p]} {s}, costs about {gold(extra)} more." for p, (s, extra) in c.next_stop.items()]
    return out
