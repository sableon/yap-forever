"""A budget as a goal: each route ends at the last stop its gold reaches.

Stops are the rank caps (75, 150, 225, 300) and each profession's own target; a recipe goal's last stop is its skill
and the recipe crafted once (#96). The gold a route needs is, with
Budget.pay "upfront" (the default), the shopping list's "Gold to bring" (whole crafts with the buffer, patterns and
fees, everything bought before you start), so the cut route always fits the list the player shops from; with
"as_you_go", the gold enough up front when crafts are sold to a vendor as you go (shopping.gold_as_you_go, the line
under "Gold to bring"). A craft's vendor price makes a route cheaper in the end but can make it need more of that gold,
so a stop the route misses may be reached by the route planned without that credit (#97).
"""
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from yap_forever.compare import settle_routes
from yap_forever.config import Budget
from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import gold
from yap_forever.planner import Plan
from yap_forever.shopping import gold_as_you_go, gold_to_bring

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
    why it stops); start: the skills the route starts from; stops_early: profession -> (the skill its route
    stalls at below the target, why), when it does. credited: the plan is the mode's route planned with the vendor
    price of the crafts sold (False: the one planned without it, which fit the budget where that one didn't).
    planned_once: profession -> the goal recipe the plan crafts once (only at the goal stop, #96); recipes: profession
    -> (skill, name) of each recipe goal; goal_extra: a recipe-goal profession the cut stops below -> what its goal
    costs on top, when the route reaches it."""
    caps: dict[int, int]
    plan: Plan
    spent: float
    next_stop: dict[int, tuple[int, float]]
    stalled: dict[int, str]
    planned_caps: dict[int, int] = field(default_factory=dict)
    start: dict[int, int] = field(default_factory=dict)
    stops_early: dict[int, tuple[int, str]] = field(default_factory=dict)
    credited: bool = True
    planned_once: dict[int, int] = field(default_factory=dict)
    recipes: dict[int, tuple[int, str]] = field(default_factory=dict)
    goal_extra: dict[int, float] = field(default_factory=dict)

    @property
    def covered(self) -> set[int]:
        """The recipe-goal professions whose goal recipe the route crafts."""
        return {p for p, spell in self.planned_once.items() if p in self.recipes and crafted(self.plan, p, spell)}

    @property
    def below_first_stop(self) -> bool:
        """No profession advances, and one could with more gold: the route is empty because of the budget
        (not because every target is reached or every profession is stalled)."""
        return bool(self.next_stop) and all(self.caps[p] <= self.start.get(p, self.caps[p]) for p in self.caps)


def key(caps: dict[int, int], once: dict[int, int] | None = None) -> tuple:
    """The cache key of a set of caps and the goal recipes crafted once there (see cut's `cache`)."""
    k = tuple(sorted(caps.items()))
    return (k, tuple(sorted(once.items()))) if once else k


def crafted(plan: Plan, prof: int, spell: int) -> bool:
    """The plan crafts `spell`, the goal recipe of `prof`, once (planner's craft-once step): its skill is not enough,
    since the craft itself can fail (Favor, a tool, materials)."""
    return any(s.profession == prof and s.spell_id == spell and s.skill_from == s.skill_to for s in plan.steps)


def copper(budget: Budget) -> int:
    """The budget in copper, as a route's gold to bring is compared with it."""
    return round(budget.gold * COPPER_PER_GOLD)  # 1.13g is 11299.999... copper in floating point


def _held(caps: dict[int, int], start: dict[int, int], below, crafts=()) -> set[str]:
    """The planner's "<Prof> already at N" events of the professions the budget holds at their start skill (caps:
    the caps planned to; below: the professions whose target is above their start): their target isn't reached,
    so the guide mustn't say there is nothing to plan. crafts: the professions whose goal recipe the route crafts
    once (#96): one already at its skill has that craft to plan."""
    return ({f"{PROFESSIONS[x]} already at {start[x]}" for x in below if caps.get(x) == start.get(x)}
            | {f"{PROFESSIONS[x]} already at {start[x]}" for x in crafts if x in start})


def adopt(c: BudgetCut, plan: Plan, spent: float) -> BudgetCut:
    """The cut with `plan`, the route planned to the same caps without some trips (plan.take_free_skips), as its
    route, and spent its gold to bring: each next stop, and each recipe goal it stops below, costs what it did, so its
    extra is counted from the new gold; the professions the budget holds at their start keep no "already at" event (in a copy of `plan` when it
    has one, else `plan` itself)."""
    held = _held(c.planned_caps, c.start, c.next_stop, c.planned_once)  # held at the start (a next stop and its start
    # as the cap), or crafting its goal recipe
    if held & set(plan.events):  # a copy: the plan given may be a cached one
        plan = dataclasses.replace(plan, events=[e for e in plan.events if e not in held])
    return dataclasses.replace(c, plan=plan, spent=spent,
                               next_stop={p: (s, extra + c.spent - spent) for p, (s, extra) in c.next_stop.items()},
                               goal_extra={p: extra + c.spent - spent for p, extra in c.goal_extra.items()})


def gold_measure(budget: Budget | None, gd, market, stock) -> Callable[[Plan], float]:
    """The gold a route needs, as a budget is compared with it (copper): "Gold to bring" for pay "upfront" (and without
    a budget), the as-you-go figure for "as_you_go". The budget's cut, its free skips and the gold the cut route spends
    all use this one."""
    if budget is not None and budget.pay == "as_you_go":
        return lambda p: gold_as_you_go(p, gd, market, stock)
    return lambda p: gold_to_bring(p, gd, market, stock)


def cut(inputs, mode: str, budget: Budget, gold_of: Callable[[Plan], float] | None = None,
        cache: dict | None = None) -> BudgetCut:
    """The `mode` route ("gold" or "value") cut at the last stops `budget` reaches.

    Stops are taken one at a time, each checked on a route planned again to it: with budget.order, the first
    profession takes its stops while the next one fits, then the second takes what is left; side by side,
    the profession with the lower stop goes first, and when its next stop doesn't fit the other one's may
    (the gold left goes to it). A stop is taken only when gold_of(route) fits the budget, so the next stop
    of each profession is the one that doesn't: its cost is that route's gold minus the cut route's.
    The route to a set of caps is the mode's route planned with the vendor credit when its gold fits, else the one
    planned without it (plan.candidates(..., vendor_credit=False), settled by the same measure) when that fits; when
    neither fits, the one that needs less gold, which is what the stop costs. The one without the credit is taken only
    when it gets each profession as far as the credited one does.
    gold_of: the gold a route needs (default gold_measure: "Gold to bring", or the as-you-go figure with budget.pay
    "as_you_go"); every comparison here uses it, the fallback's included.
    inputs: plan.PlanInputs with the targets as caps; a recipe goal (inputs.craft_once, #96) is cut like a skill target
    whose last stop is its recipe's skill with the recipe crafted once: only that stop's route crafts it, so a lower
    stop has no "did not reach" stall. A recipe whose skill the character already has is one stop, the craft.
    cache: key(caps, goal recipes crafted once) -> (routes, same, the routes without the vendor credit or None) from
    compare.settle_routes, and ("gold", mode, that key, credited, budget.pay) -> that route's gold,
    shared by both modes' cuts (planning a set of caps takes seconds); give it the routes to the targets when the
    caller has them. The routes without the credit are planned only when a credited route misses the budget."""
    from yap_forever.plan import candidates  # plan imports this module
    gold_of = gold_measure(budget, inputs.gd, inputs.market, inputs.stock) if gold_of is None else gold_of
    inputs = dataclasses.replace(inputs, order=budget.order)
    cache = {} if cache is None else cache
    limit = copper(budget)
    target = dict(inputs.caps)
    start = {p: max(1, inputs.stock.skills.get(p, 1)) for p in target}
    once = {p: s for p, s in inputs.craft_once.items() if p in target}  # the recipe goals, crafted at their goal stop
    names = {p: (target[p], inputs.gd.recipes[s].name) for p, s in once.items() if s in inputs.gd.recipes}

    def routes(caps, crafts, credited=True):
        """mode -> the route to caps crafting the goal recipes `crafts` once, planned with the vendor credit or without
        it (filled in when first asked)."""
        k = key(caps, crafts)
        sub = dataclasses.replace(inputs, caps=dict(caps), craft_once=dict(crafts))
        if k not in cache:
            cache[k] = (*settle_routes(candidates(sub), sub.caps), None)
        settled, same, bare = cache[k]
        if credited:
            return settled
        if bare is None:
            bare = settle_routes(candidates(sub, vendor_credit=False), sub.caps)[0]
            cache[k] = (settled, same, bare)
        return bare

    def gold_at(caps, crafts, credited):
        k = ("gold", mode, key(caps, crafts), credited, budget.pay)  # the figure the budget is compared with
        if k not in cache:
            cache[k] = gold_of(routes(caps, crafts, credited)[mode])
        return cache[k]

    def ends(full):
        """(each profession's stops on the route to the targets, the professions it can't advance, where it stalls
        below the target)."""
        stops, stalled, early = {}, {}, {}
        for p, t in target.items():
            end = full.final_skill.get(p, start[p])
            stops[p] = stops_for(start[p], min(t, end))
            if p in once and start[p] >= t:  # the recipe's skill is already there: one stop, the craft
                stops[p] = [t]
            if not stops[p] and start[p] < t and p in full.stall_reasons:
                stalled[p] = full.stall_reasons[p]
            elif stops[p] and end < t and p in full.stall_reasons:
                early[p] = (end, full.stall_reasons[p])
        return stops, stalled, early

    stops, stalled, early = ends(routes(target, once)[mode])

    def caps_at(level):
        """level: profession -> stops taken. With all of them the cap is the target, so a profession the
        route stalls keeps its stall reason."""
        return {p: target[p] if n == len(stops[p]) else stops[p][n - 1] if n else start[p]
                for p, n in level.items()}

    def crafts_at(level):
        """The goal recipes crafted once at `level`: those whose profession takes all its stops."""
        return {p: s for p, s in once.items() if level[p] == len(stops[p])}

    def plan_at(level):
        caps, crafts = caps_at(level), crafts_at(level)
        credited = (gold_at(caps, crafts, True) <= limit or gold_at(caps, crafts, False) >= gold_at(caps, crafts, True)
                    or not _as_far(routes(caps, crafts, False)[mode], routes(caps, crafts)[mode], caps, crafts))
        p = routes(caps, crafts, credited)[mode]
        held = _held(caps, start, [x for x in caps if start[x] < target[x] or x in once], crafts)
        p.events = [e for e in p.events if e not in held]  # held at the start by the budget: not a target reached
        return p, gold_at(caps, crafts, credited)

    def made(level, plan, spent, next_stop):
        """The cut at `level`, with what each recipe goal it stops below costs on top (when its route crafts it)."""
        extra = {}
        for p, spell in once.items():
            if level[p] < len(stops[p]) and p not in stalled and p not in early:
                goal, gold = plan_at({**level, p: len(stops[p])})
                if crafted(goal, p, spell):
                    extra[p] = gold - spent
        return BudgetCut(reached(level), plan, spent, next_stop, stalled, caps_at(level), start, early,
                         plan.vendor_credit, crafts_at(level), names, extra)

    def reached(level):
        return {p: stops[p][n - 1] if n else start[p] for p, n in level.items()}

    level = {p: len(stops[p]) for p in target}
    plan, spent = plan_at(level)
    if spent <= limit:
        if not plan.vendor_credit:  # the route without the credit may get further than the one the stops came from
            stops, stalled, early = ends(plan)
            level = {p: len(stops[p]) for p in target}
        return made(level, plan, spent, {})

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
    return made(level, plan, spent, next_stop)


def _as_far(p: Plan, than: Plan, caps: dict[int, int], crafts: dict[int, int] | None = None) -> bool:
    """p gets every profession in caps at least as far as `than` does, and crafts each goal recipe in `crafts` that
    `than` crafts."""
    return (all(p.final_skill.get(x, 0) >= than.final_skill.get(x, 0) for x in caps)
            and all(crafted(p, x, s) or not crafted(than, x, s) for x, s in (crafts or {}).items()))


def amount(budget: Budget) -> str:
    """The budget as the player gave it: '30g', '12.5g'."""
    return f"{budget.gold:.2f}".rstrip("0").rstrip(".") + "g"


def not_planned(other: int, goal: int) -> str:
    """Said when a budget with a recipe goal on `goal` leaves the other profession unplanned (#96)."""
    return f"{PROFESSIONS[other]} is not planned with this budget: it goes to the {PROFESSIONS[goal]} goal."


def lines(c: BudgetCut, budget: Budget) -> list[str]:
    """What the budget reaches, why a profession gets none of it, and what each next stop costs on top (and,
    when the route stalls at that stop, why). With every target reached and no stall, nothing to say.
    A recipe goal (#96) the route crafts: "<budget> covers <Prof> to <skill> and one <recipe> (<gold>)." when every
    goal is covered; one the cut stops below: "The goal, <Prof> <skill> and one <recipe>, costs about <gold> more.",
    instead of its next stop's line when that stop is the goal."""
    b = amount(budget)
    covered = c.covered
    moved = [p for p in c.caps if c.caps[p] > c.start.get(p, c.caps[p]) or p in covered]
    out = []
    if moved:
        how = ", selling crafts to a vendor as you go" if budget.pay == "as_you_go" else ""  # c.spent's figure
        verb = "covers" if all(p in covered for p in c.caps) else "takes"
        parts = [f"{PROFESSIONS[p]} to {c.caps[p]}" + (f" and one {c.recipes[p][1]}" if p in covered else "")
                 for p in moved]
        joint = ", and " if covered and len(parts) > 1 else " and "
        out.append(f"{b} {verb} " + joint.join(parts) + f" ({gold(c.spent)}{how}).")
    elif c.below_first_stop:
        out.append(f"{b} doesn't reach the first stop: nothing is planned yet.")
    for p, extra in c.goal_extra.items():
        skill, name = c.recipes[p]
        out.append(f"The goal, {PROFESSIONS[p]} {skill} and one {name}, costs about {gold(extra)} more.")
    for p, why in c.stalled.items():
        out.append(f"{PROFESSIONS[p]} gets none of it: {_reason(p, why)}.")
    for p, (s, extra) in c.next_stop.items():
        if p in c.goal_extra and s == c.recipes[p][0]:  # the goal is the next stop: said above
            continue
        end, why = c.stops_early.get(p, (None, ""))
        tail = f"; the route stops there: {_reason(p, why)}" if s == end else ""
        out.append(f"The next stop, {PROFESSIONS[p]} {s}, costs about {gold(extra)} more{tail}.")
    return out


def _reason(prof: int, why: str) -> str:
    """A stall reason without its profession name ("Enchanting: no usable recipe at 1")."""
    return why.removeprefix(PROFESSIONS[prof] + ": ")
