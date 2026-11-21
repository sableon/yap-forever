"""Greedy route: at each skill point, craft the recipe with the lowest net cost."""
import dataclasses
import math
import re
from collections import ChainMap
from dataclasses import dataclass, field

from yap_forever.costmodel import VENDOR_TOOLS, Cost, Pools, bars_to_ore, money, skillup_chance
from yap_forever.disenchant import DE_THRESHOLDS, de_skill_needed, de_yield
from yap_forever.gamedata import ENCH, PROFESSIONS
from yap_forever.shared import allocate, mail_used

START_CAP = 75  # Apprentice
ALREADY_AT = re.compile(r"^(.+) already at (\d+)$")  # the event _Route.run records for a target reached
DISENCHANT = 0  # Step.spell_id of an Enchanting skill-up from disenchanting
BUFFER = 1.15  # extra crafts on yellow and green steps, which are expected values, not promises


def buffer_factor(crafts: float) -> float:
    """1.15 for a step that may need more than one craft (yellow or green), 1 for an orange one."""
    return BUFFER if crafts > 1 + 1e-9 else 1.0


def step_factor(step) -> float:
    """Buffered crafts over expected crafts for a step that may span several skill points."""
    if step.buffered is None or not step.crafts:
        return buffer_factor(step.crafts)
    return step.buffered / step.crafts


@dataclass
class Step:
    profession: int
    skill_from: int
    skill_to: int
    spell_id: int
    name: str
    crafts: float
    cash: float
    economic: float
    materials: dict[int, float] = field(default_factory=dict)  # from bank, farm, AH or vendor
    from_stock: dict[int, float] = field(default_factory=dict)  # part of materials from your bank
    used_made: dict[int, float] = field(default_factory=dict)  # your own crafts or disenchants used
    buffered: float | None = None  # crafts with the buffer, judged one skill point at a time
    extra: dict[int, float] = field(default_factory=dict)  # taken once, not per craft (part of materials):
    # quest hand-ins and a crafted tool's materials
    tools_bought: dict[int, float] = field(default_factory=dict)  # tools bought for this step (AH or vendor)
    from_mail: dict[int, float] = field(default_factory=dict)  # part of materials mailed by your other characters
    tools_mailed: dict[int, float] = field(default_factory=dict)  # tools another of your characters mails you


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    bought: dict[int, float] = field(default_factory=dict)
    vendor_bought: dict[int, float] = field(default_factory=dict)
    used_stock: dict[int, float] = field(default_factory=dict)
    used_mail: dict[int, list[tuple[str, int]]] = field(default_factory=dict)  # item -> (character, count) mailed to you
    shared: dict[str, dict[int, int]] = field(default_factory=dict)  # your other characters' mailable items, by name
    farmed_bars: dict[int, float] = field(default_factory=dict)
    farm: dict[int, int] = field(default_factory=dict)  # ore -> count
    held_for_de: dict[int, tuple[float, int]] = field(default_factory=dict)
    de_materials: dict[int, float] = field(default_factory=dict)
    leftovers: dict[int, float] = field(default_factory=dict)  # produced, never used
    kept_greens: dict[int, float] = field(default_factory=dict)  # leftovers kept to disenchant elsewhere
    fees: float = 0
    favor_spent: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)
    stalled: dict[int, int] = field(default_factory=dict)
    stall_reasons: dict[int, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    ranks: list[tuple[int, int, int, float]] = field(default_factory=list)  # (profession, skill, new cap, fee)
    learn_log: list[tuple[int, int, int, str]] = field(default_factory=list)  # (profession, skill, spell, how)
    final_skill: dict[int, int] = field(default_factory=dict)
    learned: list[int] = field(default_factory=list)
    crafted: dict[int, float] = field(default_factory=dict)  # intermediates crafted for reagents
    cash_total: float = 0
    economic_total: float = 0
    sale_proceeds: float = 0  # what the leftovers sold bring: on the AH up to the sale limit, the rest to a vendor
    leftover_value: float = 0
    vendor_back: float = 0  # the leftovers sold, every one at its vendor price, whatever the AH pays (#97)
    vendor_credit: bool = True  # planned with the vendor price of the crafts sold in the score (False: see plan())
    other_crafts: dict[int, int] = field(default_factory=dict)  # intermediates crafted with a profession the route
    # doesn't plan (plan()'s `fixed`, #96): item -> the recipe

    @property
    def ah_extra(self) -> float:
        """What AH sales of the crafts bring on top of their vendor price: never counted in choosing the route."""
        return self.sale_proceeds - self.vendor_back

    @property
    def net_gold(self) -> float:
        """Gold out of pocket less what vendors pay back for the crafts: the least-gold measure."""
        return self.cash_total - self.vendor_back

    def sold(self, item: int) -> bool:
        """A leftover the route sells: not held for disenchanting, not a green kept for another character's
        Enchanting, not a disenchant material (those count at their worth, see _Route._finish)."""
        return item not in self.held_for_de and item not in self.kept_greens and item not in self.de_materials


def reached_lines(plan) -> list[str]:
    """One line for each target the character already has (the planner's "<Prof> already at N" events),
    for the guide and the report to say instead of showing an empty route."""
    return [f"{m.group(1)} is already at {m.group(2)}: nothing to plan."
            for e in plan.events if (m := ALREADY_AT.match(e))]


def measure(mode: str):
    """The measure a route of `mode` is chosen and compared by, as a function of a Plan: for "gold" the gold out of
    pocket less what vendors pay back for the crafts (Plan.net_gold), for "value" the total value (crafts sold at
    their vendor price; AH resale never counts). Settling the routes, the skip alternatives, free skips and the
    listed saving all use it."""
    return (lambda p: p.net_gold) if mode == "gold" else (lambda p: p.economic_total)


def crafted(plan, prof: int, spell: int) -> bool:
    """The plan crafts `spell`, the goal recipe of `prof`, once (the craft-once step): its skill is not enough, since
    the craft itself can fail (Favor, a tool, materials)."""
    return any(s.profession == prof and s.spell_id == spell and s.skill_from == s.skill_to for s in plan.steps)


def does_what_was_asked(plan, caps: dict[int, int], once: dict[int, int] | None = None, than=None) -> bool:
    """The route does what was asked: every profession in `caps` reaches its skill there and every goal recipe in
    `once` (profession -> recipe crafted once) is crafted. With `than`, another route of the same targets: as far as
    that one gets instead, each profession in `caps` at least at its final skill and each goal recipe it crafts
    crafted too. Settling the routes, the skip alternatives (so free skips), a budget's fallback route and the listed
    saving all ask it."""
    if than is not None:
        caps = {x: than.final_skill.get(x, 0) for x in caps}
        once = {x: s for x, s in (once or {}).items() if crafted(than, x, s)}
    return (all(plan.final_skill.get(x, 0) >= c for x, c in caps.items())
            and all(crafted(plan, x, s) for x, s in (once or {}).items()))


def resolve_goals(goals: dict, gd, favor=None, quests: dict | None = None) -> tuple[dict[int, int], dict[int, int]]:
    """Goals (config.Goal per profession) -> (target skill per profession, recipe to craft once)."""
    caps: dict[int, int] = {}
    once: dict[int, int] = {}
    favor_spells = set(favor.recipes) if favor else set()
    quests = quests or {}
    for prof, goal in goals.items():
        if goal.recipe is None:
            caps[prof] = goal.skill
            continue
        name = PROFESSIONS.get(prof, str(prof))
        text = goal.recipe.strip()
        mine = [r for r in gd.recipes.values() if r.skill_line == prof]
        r = next((r for r in mine if (text.isdigit() and r.spell_id == int(text))
                  or r.name.casefold() == text.casefold()), None)
        if r is None:
            raise ValueError(f"no {name} recipe called {text!r}")
        if r.source == "unknown" and r.spell_id not in favor_spells and r.spell_id not in quests:
            raise ValueError(f"can't plan {r.name} yet: the game data doesn't say how to learn it")
        if r.spell_id in favor_spells:  # the skill the planner will use for a Favor recipe
            r = apply_favor({r.spell_id: r}, favor)[r.spell_id]
        caps[prof], once[prof] = r.required_skill, r.spell_id
    return caps, once


def apply_favor(recipes: dict, favor) -> dict:
    """Recipes listed in favor.toml are learned with Favor.

    Forever sells these as scroll items for Favor, so game data may call them "scroll"."""
    out = dict(recipes)
    for spell in favor.recipes:
        r = out.get(spell)
        if not r or r.source not in ("unknown", "scroll"):
            continue
        # Without a known skill, a placeholder orange of 1 is not trusted: use yellow.
        req = favor.skills.get(spell, r.required_skill if r.thresholds[0] > 1 else r.thresholds[1])
        out[spell] = dataclasses.replace(r, source="favor", required_skill=req)
    return out


def plan(gd, valuer, stock, favor, caps: dict[int, int], quests: dict | None = None,
         reuse: dict[int, tuple[float, float]] | None = None,
         craft_once: dict[int, int] | None = None, exclude: frozenset[int] = frozenset(),
         one_time_in_full: bool = False, overtime: int = 0, reading: str = "relative",
         order: tuple[int, ...] | None = None, vendor_credit: bool = True,
         fixed: dict[int, int] | None = None) -> Plan:
    """caps: profession -> target skill (one or two professions; see resolve_goals).
    order: None raises the professions side by side (always the lower one); skill lines raise them one
    at a time, the first in the order until it reaches its cap or stalls, then the next.
    craft_once: profession -> recipe crafted once on reaching its cap. exclude: recipes not to use.
    one_time_in_full: in gold mode, charge a recipe's one-time costs (pattern, fee, tools) in full
    rather than spread over the points it could cover (a candidate route; see compare.settle_routes).
    reuse: item -> (count later steps consume, value per unit), credited when a step makes it.
    overtime, reading: the character's Working Overtime rank and how it reads (see skillup_chance);
    it raises the chance of every skill-up, disenchanting included.
    vendor_credit: False plans without the vendor price of the crafts sold in the score (a budget's fallback route,
    which may need less of the gold the budget is compared with; see budget.cut). The totals count what vendors pay back either way, and the
    plan says how it was planned (Plan.vendor_credit), so a route planned again from it is planned the same way.
    fixed: profession -> skill of a profession the route doesn't plan (a budget with a recipe goal on the other one,
    #96): no steps or skill-ups, but its trainer and starter recipes up to that skill count as known and may craft
    the route's reagents when that beats buying by the craft margin (costmodel.Valuer._take), at no fee. It is never
    in final_skill; what it crafts is in Plan.other_crafts."""
    return _Route(gd, valuer, stock, favor, caps, quests, reuse, craft_once, exclude, one_time_in_full,
                  overtime, reading, order, vendor_credit, fixed).run()


class _Route:
    """The state one plan() call shares between its steps."""

    def __init__(self, gd, valuer, stock, favor, caps, quests, reuse, craft_once, exclude,
                 one_time_in_full, overtime, reading, order=None, vendor_credit=True, fixed=None):
        self.gd, self.valuer, self.stock, self.favor = gd, valuer, stock, favor
        self.vendor_credit = vendor_credit
        self.order = tuple(order) if order else None
        self.one_time_in_full, self.overtime, self.reading = one_time_in_full, overtime, reading
        self.quests = quests or {}
        self.reuse = reuse or {}
        self.caps = dict(caps)
        self.craft_once = craft_once or {}
        self.profs = tuple(self.caps)
        self.has_ench = ENCH in self.caps
        self.ench_cap = self.caps.get(ENCH, 0)
        recipes = apply_favor(gd.recipes, favor)
        for spell in self.quests:
            if spell in recipes:
                recipes[spell] = dataclasses.replace(recipes[spell], source="quest")
        for spell in exclude:
            recipes.pop(spell, None)
        self.recipes = recipes
        self.pools = Pools.from_stock(stock)
        self.p = Plan(vendor_credit=vendor_credit)
        skill = {x: max(1, stock.skills.get(x, 1)) for x in self.profs}
        self.skill = skill
        # #96: the professions not planned, at their fixed skill, for the Valuer only (C43): never in profs or
        # final_skill; their trainer recipes up to it are known (in learned, below)
        self.fixed = {x: s for x, s in (fixed or {}).items() if x not in self.caps}
        self.known = ChainMap(skill, self.fixed) if self.fixed else skill  # the skills the Valuer crafts with
        # Ranks up to the current skill are already trained; at exactly a cap the next one is not.
        self.rank_cap = {x: min([c for c in [START_CAP] + [r.cap for r in gd.trainer_ranks.get(x, [])]
                                 if c >= skill[x]], default=START_CAP) for x in self.profs}
        self.learned: set[int] = {r.spell_id for r in recipes.values() if r.skill_line in self.fixed
                                  and r.source == "trainer" and r.required_skill <= self.fixed[r.skill_line]}
        self.produced: dict[int, float] = {}
        self.held: dict[int, float] = {}
        self.skipped: dict[int, str] = {}
        self.soft_stalls: set[int] = set()  # stalled for lack of materials; retried when new ones appear
        self.spent = Cost()
        self.favor_left = stock.favor
        self.de_credit = 0.0  # disenchants done that have not yet added up to a skill-up
        self.ench_reagents = ({i for r in recipes.values() if r.skill_line == ENCH for i in r.reagents}
                              if self.has_ench else set())
        # held item -> (count mailed by other characters, their names)
        self.held_mail: dict[int, tuple[float, str]] = {}

    def run(self) -> Plan:
        for x in self.profs:
            if self.skill[x] >= self.caps[x]:
                self.p.events.append(f"{PROFESSIONS[x]} already at {self.skill[x]}")

        self._disenchant_bank()
        while True:
            active = [x for x in self.profs if x not in self.p.stalled and self.skill[x] < self.caps[x]]
            if not active:
                break
            prof = (next((x for x in self.order if x in active), None) if self.order else None) \
                or min(active, key=lambda x: (self.skill[x], x))
            s = self.skill[prof]
            name = PROFESSIONS[prof]

            if s >= self.rank_cap[prof]:
                self._rank_step(prof, s, name)
                continue

            best = self._best_recipe(prof, s)
            if best is None:
                self.p.stalled[prof], self.p.stall_reasons[prof] = s, f"{name}: no usable recipe at {s}"
                self.soft_stalls.add(prof)
                continue

            done = self._commit(prof, s, name, best)
            if done is None:
                continue
            step_cost, parts, made_something = done
            self._merge_step(prof, s, best[1], best[2], step_cost, parts)
            self.skill[prof] = s + 1
            self._after_step(prof, made_something)

        for prof, spell in self.craft_once.items():
            self._craft_once_step(prof, spell)

        return self._finish()

    def _may_use(self, r) -> bool:
        """Merchant's Favor recipes are personal-use rewards: never used to level or to make a tool, unless the
        recipe is its profession's craft-once goal (favor_suggest lists the others to craft once)."""
        return r.source != "favor" or self.craft_once.get(r.skill_line) == r.spell_id

    def _tool_held(self, cat):
        return any(self.gd.satisfies(i, cat) for i in self.pools.held())

    def _learn_option(self, r):
        """(Cost, favor, scroll purchase kind, quest hand-ins) to learn r, or a reason string."""
        if r.spell_id in self.learned or r.source == "starter":
            return Cost(), 0, None, []
        if r.source == "trainer":
            return Cost(r.fee, r.fee), 0, None, []
        if r.source == "scroll":
            if r.scroll_item and self.pools.stock.get(r.scroll_item, 0) >= 1:
                # your own pattern: no cash, used up; the value modes give up what it would sell for,
                # as for any owned item (Valuer._take)
                v = self.valuer.owned_value(r.scroll_item)
                return Cost(0, v, v), 0, "owned", []
            if r.scroll_item and self.pools.mail.get(r.scroll_item, 0) >= 1:
                # a pattern another of your characters mails you: the same, taken from what they hold
                v = self.valuer.owned_value(r.scroll_item)
                return Cost(0, v, v), 0, "mail", []
            opt = self.valuer.buy_option(r.scroll_item, 1, self.pools.bought.get(r.scroll_item, 0))
            if opt is None:
                return f"scroll not available: {self.gd.name(r.scroll_item)}"
            return Cost(opt[1], opt[1]), 0, opt[0], []
        if r.source == "favor":
            price = self.favor.recipes[r.spell_id]
            return (Cost(), price, None, []) if price <= self.favor_left else f"not enough Favor ({price})"
        if r.source == "quest":
            if self.stock.level < self.quests[r.spell_id].level:
                return f"quest needs character level {self.quests[r.spell_id].level}"
            reqs = list(self.quests[r.spell_id].items.items())
            c = self.valuer.take_many(reqs, self.pools, self.known, commit=False, learned=self.learned)
            if c is None:
                return "quest items not available: " + ", ".join(self.gd.name(i) for i, _ in reqs)
            return c, 0, None, reqs  # hand-ins are taken together with the first crafts
        return "no known source"

    def _tool_option(self, cat):
        """Cheapest way to get a missing tool, as a dict, or None."""
        item = self.gd.tool_items.get(cat)
        if item is None:
            return None
        opts = []
        mailed = next((i for i in sorted(self.pools.mail) if self.pools.mail[i] >= 1 and self.gd.satisfies(i, cat)),
                      None)
        if mailed is not None:  # a tool another of your characters holds: no cash, and it is not used up
            opts.append({"how": "mail", "item": mailed, "cost": Cost(), "requests": [], "recipe": None})
        if item in VENDOR_TOOLS and item in self.gd.items:
            c = self.gd.items[item].buy_price
            opts.append({"how": "vendor", "item": item, "cost": Cost(c, c), "requests": [], "recipe": None})
        ah = self.valuer.buy_option(item, 1, self.pools.bought.get(item, 0))
        if ah and ah[0] == "ah":
            opts.append({"how": "ah", "item": item, "cost": Cost(ah[1], ah[1]), "requests": [], "recipe": None})
        for r in self.recipes.values():
            if not r.output or r.output[0] != item or self.skill.get(r.skill_line, 0) < r.required_skill:
                continue
            if not self._may_use(r):
                continue
            if any(not self._tool_held(c) for c in r.tools):
                continue
            lo = self._learn_option(r)
            if isinstance(lo, str):
                continue
            reqs = [(i, q / r.output[1]) for i, q in r.reagents.items()]
            c = self.valuer.take_many(reqs, self.pools, self.known, commit=False, learned=self.learned)
            if c is not None:
                opts.append({"how": "craft", "item": item, "cost": lo[0], "requests": reqs,
                             "recipe": r, "peek": c})
        if not opts:
            return None
        return min(opts, key=lambda o: o["cost"].economic + (o["peek"].score if "peek" in o else 0))

    def _tools_to_get(self, r):
        """The tools r needs that are not held, each the cheapest way to get it: (tools, None), or
        (None, the first tool category that can't be bought or made)."""
        tools = []
        for cat in r.tools:
            if self._tool_held(cat):
                continue
            t = self._tool_option(cat)
            if t is None:
                return None, cat
            tools.append(t)
        return tools, None

    def _release_held(self, where=""):
        released = False
        if not self.has_ench:
            return released
        for item in list(self.held):
            gate = de_skill_needed(self.gd.items[item].item_level)
            if self.skill[ENCH] >= gate:
                n = self.held.pop(item)
                for mat, per in de_yield(self.gd.items[item]).items():
                    self.pools.made[mat] = self.pools.made.get(mat, 0) + n * per
                    self.p.de_materials[mat] = self.p.de_materials.get(mat, 0) + n * per
                if item in self.held_mail:  # say which part is mailed, and by whom
                    mailed_n, who = self.held_mail.pop(item)
                    src = (f" (mail from {who})" if mailed_n >= n - 1e-9
                           else f" ({n - mailed_n:.0f} your own, {mailed_n:.0f} mail from {who})")
                else:
                    src = where
                self.p.events.append(f"Enchanting {self.skill[ENCH]}: disenchant {n:.0f} {self.gd.name(item)}{src}")
                self._de_skillups(n)
                released = True
        return released

    def _de_skillups(self, n):
        """Disenchanting n items gives Enchanting skill-ups at the expected rate."""
        self.de_credit += n
        while self.skill[ENCH] < min(self.ench_cap, self.rank_cap[ENCH]):
            s = self.skill[ENCH]
            chance = skillup_chance(s, DE_THRESHOLDS, self.overtime, self.reading)
            if chance <= 0:
                self.de_credit = 0.0
                return
            need = 1 / chance
            if self.de_credit + 1e-9 < need:
                return
            self.de_credit -= need
            last = next((x for x in reversed(self.p.steps) if x.profession == ENCH), None)
            if last and last.spell_id == DISENCHANT and last.skill_to == s:
                last.skill_to, last.crafts, last.buffered = s + 1, last.crafts + need, last.buffered + need
            else:  # no buffer: the count is limited by the greens you have
                self.p.steps.append(Step(ENCH, s, s + 1, DISENCHANT, "Disenchant greens", need, 0, 0, buffered=need))
            self.skill[ENCH] = s + 1

    def _disenchant_bank(self):
        """Greens in the bank are disenchanted first, all at once: a green you can disenchant is not a
        lost sale, and each one is a chance at an Enchanting skill-up below 60. Then the greens another of
        your characters can mail you, after your own (their source is named)."""
        if not self.has_ench or self.skill[ENCH] >= self.ench_cap:
            return

        def greens_of(pool):
            return {i: n for i, n in pool.items() if n >= 1 and (info := self.gd.items.get(i))
                    and de_yield(info) and de_skill_needed(info.item_level) <= self.ench_cap}

        greens, mailed = greens_of(self.pools.stock), greens_of(self.pools.mail)
        if not greens and not mailed:
            return
        for i, n in greens.items():
            del self.pools.stock[i]
            self.held[i] = self.held.get(i, 0) + n
        first = len(self.p.steps)
        if greens:
            self._release_held(" from your bank")
        for i, n in mailed.items():  # each one says whose it is
            del self.pools.mail[i]
            self.held[i] = self.held.get(i, 0) + n
            who = ", ".join(name for name, _n in allocate(getattr(self.stock, "shared", {}), i, math.ceil(n - 1e-9)))
            self.held_mail[i] = (n, who)
            self._release_held()
        if len(self.p.steps) > first:  # show the greens on the first disenchant step and in the keep table
            self.p.steps[first].materials = {**greens, **mailed}
            self.p.steps[first].from_stock = dict(greens)
            self.p.steps[first].from_mail = dict(mailed)

    def _de_within_target(self, item):
        """Enchanting is planned and reaches the skill this item needs to be disenchanted."""
        info = self.gd.items.get(item)
        return self.has_ench and info is not None and de_skill_needed(info.item_level) <= self.ench_cap

    def _should_hold(self, item, opts):
        if not self._de_within_target(item):
            return False
        if max(opts, key=opts.get) == "de":
            return True
        info = self.gd.items.get(item)
        # While disenchanting still gives Enchanting skill, that beats selling the green.
        if de_yield(info) and (de_skill_needed(info.item_level) <= self.skill[ENCH]
                               < min(self.ench_cap, DE_THRESHOLDS[3])):
            return True
        # Disenchanting is the only source of an Enchanting reagent missing from the AH.
        return any(m in self.ench_reagents and self.valuer.market.depth(m) == 0 for m in de_yield(info))

    def _output_fate(self, item, n, opts, hold=None, reuse_left=0.0):
        """How n units of a craft's output count, each once: (reused by later steps, up to reuse_left; kept: held for
        this route's disenchanting, a keep_greens green with no Enchanting planned, or a disenchant material, which
        counts at its worth; sold, to a vendor or on the AH). hold: whether the route holds the item for
        disenchanting, decided by _should_hold when not given (_finish knows it from what was held)."""
        reused = min(n, max(0.0, reuse_left))
        rest = n - reused
        if hold is None:
            hold = self._should_hold(item, opts)
        keep_green = getattr(self.stock, "keep_greens", False) and not self.has_ench and opts.get("de")
        if hold or keep_green or item in self.p.de_materials:
            return reused, rest, 0.0
        return reused, 0.0, rest

    def _learn_now(self, r, lo, s, name):
        learn_cost, favor_cost, scroll_kind, _reqs = lo
        self.learned.add(r.spell_id)
        self.p.learned.append(r.spell_id)
        self.p.learn_log.append((r.skill_line, s, r.spell_id, scroll_kind or r.source))
        if r.source == "starter":
            return Cost()
        self.favor_left -= favor_cost
        self.p.favor_spent += favor_cost
        if scroll_kind == "owned":
            self.pools.stock[r.scroll_item] -= 1  # consumed: no longer owned, sellable or bought
        elif scroll_kind == "mail":
            self.pools.mail[r.scroll_item] -= 1  # consumed: the other character no longer has it to mail
        elif scroll_kind:
            pool = self.pools.bought if scroll_kind == "ah" else self.pools.vendor
            pool[r.scroll_item] = pool.get(r.scroll_item, 0) + 1
        if r.source == "quest":
            q = self.quests[r.spell_id]
            items = ", ".join(f"{n} {self.gd.name(i)}" for i, n in q.items.items())
            self.p.events.append(f"{name} {s}: Learn {r.name} (quest from {q.giver}: hand in {items}; level {q.level})")
            return Cost()  # the hand-ins are taken and costed with the crafts
        pattern = {"owned": "your own pattern", "mail": "a pattern mailed by another of your characters"}
        how = {"trainer": "trainer", "scroll": pattern.get(scroll_kind, "scroll"),
               "favor": f"{favor_cost} Favor"}[r.source]
        price = f" {money(learn_cost.cash)}" if learn_cost.cash else ""
        self.p.events.append(f"{name} {s}: Learn {r.name} ({how}{price})")
        return learn_cost

    def _train_in_window(self, prof, s, name):
        """A trainer visit to learn a recipe also trains the next rank when the skill is in its window
        and the target needs that rank."""
        nxt = self._next_rank(prof)
        if (nxt is None or self.caps[prof] <= self.rank_cap[prof] or s < nxt.required_skill
                or self.stock.level < nxt.level):
            return
        self._train_rank(prof, s, name, nxt)

    def _get_tools(self, tools, s, name):
        """Craft or buy the tools a step needs; their materials are taken with the step's.
        Returns (cost, the crafted tools' materials, the tools bought, the tools mailed by your other
        characters)."""
        cost, extra, bought, mailed = Cost(), {}, {}, {}
        for t in tools:
            item = t["item"]
            if t["how"] == "mail":
                if item not in self.pools.tools and self.pools.mail.get(item, 0) >= 1:
                    who = ", ".join(name for name, _n in allocate(getattr(self.stock, "shared", {}), item, 1))
                    self.pools.mail[item] -= 1  # it is yours now: held for the rest of the route
                    mailed[item] = mailed.get(item, 0) + 1
                    self.p.events.append(f"{name} {s}: Use tool {self.gd.name(item)} (mailed by {who})")
            elif t["how"] == "craft":
                tr = t["recipe"]
                if tr.spell_id not in self.learned:
                    cost += self._learn_now(tr, self._learn_option(tr), s, PROFESSIONS[tr.skill_line])
                self.p.events.append(f"{name} {s}: Craft tool {self.gd.name(item)}")
                for i, q in t["requests"]:
                    extra[i] = extra.get(i, 0) + q
            else:
                pool = self.pools.bought if t["how"] == "ah" else self.pools.vendor
                pool[item] = pool.get(item, 0) + 1
                cost += t["cost"]
                bought[item] = bought.get(item, 0) + 1
                self.p.events.append(f"{name} {s}: Buy tool {self.gd.name(item)} ({t['how']} {money(t['cost'].cash)})")
            self.pools.tools.add(item)
        return cost, extra, bought, mailed

    def _craft_once_step(self, prof, spell):
        """The goal recipe, learned and crafted once at the end of its profession's route."""
        name, s, r = PROFESSIONS[prof], self.skill[prof], self.recipes.get(spell)
        if r is None or s < r.required_skill:
            self.p.stall_reasons.setdefault(prof, f"{name}: did not reach {r.name if r else spell}")
            return
        lo = self._learn_option(r)
        if isinstance(lo, str):
            self.p.stall_reasons[prof] = f"{name}: can't learn {r.name}: {lo}"
            return
        tools, missing = self._tools_to_get(r)
        if missing is not None:
            self.p.stall_reasons[prof] = f"{name}: {r.name} needs a tool that can't be bought or made"
            return
        requests = [rq for t in tools for rq in t["requests"]] + lo[3] + list(r.reagents.items())
        if self.valuer.take_many(requests, self.pools, self.known, commit=False, learned=self.learned) is None:
            self.p.stall_reasons[prof] = f"{name}: materials for {r.name} not available"
            return
        step_cost = Cost()
        if spell not in self.learned:
            step_cost += self._learn_now(r, lo, s, name)
        tool_cost, extra, bought, tools_mailed = self._get_tools(tools, s, name)
        step_cost += tool_cost
        for i, q in lo[3]:
            extra[i] = extra.get(i, 0) + q
        before = _snapshot(self.pools)
        step_cost += self.valuer.take_many(requests, self.pools, self.known, commit=True, learned=self.learned)
        mats, from_stock, used_made, from_mail = _deltas(before, _snapshot(self.pools))
        if r.output:
            self.pools.made[r.output[0]] = self.pools.made.get(r.output[0], 0) + r.output[1]
        self.spent += step_cost
        self.p.steps.append(Step(prof, s, s, spell, r.name, 1, step_cost.cash, step_cost.economic,
                                 mats, from_stock, used_made, 1, extra, bought, from_mail, tools_mailed))
        self.p.events.append(f"{name} {s}: craft {r.name} once")

    def _next_rank(self, prof):
        """The trainer rank above the current one, or None."""
        return next((r for r in self.gd.trainer_ranks.get(prof, []) if r.cap > self.rank_cap[prof]), None)

    def _train_rank(self, prof, s, name, nxt):
        """Train rank nxt at skill s: its fee is paid and the cap rises."""
        self.p.fees += nxt.fee
        self.spent += Cost(nxt.fee, nxt.fee)
        self.rank_cap[prof] = nxt.cap
        self.p.ranks.append((prof, s, nxt.cap, nxt.fee))
        self.p.events.append(f"{name} {s}: train rank up to {nxt.cap} ({money(nxt.fee)})")

    def _rank_step(self, prof, s, name):
        """At the current rank's cap: train the next rank, or stall the profession when it can't be."""
        nxt = self._next_rank(prof)
        if nxt is None or nxt.required_skill > s:
            self.p.stalled[prof], self.p.stall_reasons[prof] = s, f"{name}: no next rank to train at {s}"
        elif self.stock.level < nxt.level:
            self.p.stalled[prof] = s
            self.p.stall_reasons[prof] = f"{name}: next rank needs character level {nxt.level}"
        else:
            self._train_rank(prof, s, name, nxt)

    def _best_recipe(self, prof, s):
        """The recipe to craft at skill s: (sort key, recipe, crafts per point, learn option, tools to get,
        material requests), or None. Recipes that can't be used are noted in skipped."""
        found = []  # (key, key without the vendor credit, the pick)
        for r in self.recipes.values():
            if r.skill_line != prof or r.required_skill > s or not self._may_use(r):
                continue
            chance = skillup_chance(s, r.thresholds, self.overtime, self.reading)
            if chance <= 0:
                continue
            crafts = 1 / chance
            usable = max(1, min(r.thresholds[3], self.caps[prof]) - s)
            lo = self._learn_option(r)
            if isinstance(lo, str):
                self.skipped[r.spell_id] = lo
                continue
            tools, missing = self._tools_to_get(r)
            if missing is not None:
                item = self.gd.tool_items.get(missing)
                self.skipped[r.spell_id] = f"tool not available: {self.gd.name(item) if item else missing}"
                continue
            requests = [rq for t in tools for rq in t["requests"]] + \
                [(item, q * crafts) for item, q in r.reagents.items()]
            c = self.valuer.take_many(requests, self.pools, self.known, commit=False, learned=self.learned)
            if c is not None and lo[3] and self.valuer.take_many(lo[3] + requests, self.pools, self.known,
                                                                 commit=False, learned=self.learned) is None:
                self.skipped[r.spell_id] = "not enough materials for quest and reagents"
                continue
            if c is None:
                bad = next((i for i, q in requests
                            if self.valuer.take(i, q, self.pools, self.known, commit=False,
                                                learned=self.learned) is None), None)
                self.skipped[r.spell_id] = (f"unpriceable: {self.gd.name(bad)}" if bad is not None
                                            else "not enough materials for tool and reagents")
                continue
            # Each output unit is credited once (_output_fate): reused at what it would cost, kept at its disenchant
            # value (no gold), sold at its vendor price. AH resale never counts. The vendor credit never takes the
            # craft below zero cost by itself (reuse and disenchant credits are as before) and never pulls in a
            # lower-chance craft (_pick): the route levels, it doesn't farm vendor gold.
            reuse_val = held_val = sold_val = 0
            if r.output:
                item, n = r.output[0], r.output[1] * crafts
                opts = self.valuer.output_options(item, self.produced.get(item, 0))
                # a reagent later steps consume is worth what it would cost, up to the count they need
                need, unit = self.reuse.get(item, (0.0, 0.0))
                reused, held, sold = self._output_fate(item, n, opts,
                                                       reuse_left=need - self.produced.get(item, 0))
                reuse_val = unit * reused
                held_val = held * opts.get("de", 0)
                sold_val = sold * self.valuer.vendor_price(item) if self.vendor_credit else 0
            one_time = lo[0].economic + sum(t["cost"].economic for t in tools)
            base = c.score + one_time / usable
            plain = base - reuse_val - held_val  # the score without the vendor credit
            # the vendor credit is at most what is left of the craft's cost after the reuse and disenchant credits
            score = plain - min(sold_val, max(0.0, plain))
            if self.valuer.mode == "gold":  # gold spent first; at equal gold the higher chance, then the lower value
                one_cash = lo[0].cash + sum(t["cost"].cash for t in tools)
                spread = 1 if self.one_time_in_full else usable
                cash = c.cash + one_cash / spread
                plain_gold = cash - reuse_val
                key = (round(plain_gold - min(sold_val, max(0.0, plain_gold)), 2), crafts, score, r.spell_id)
                plain_key = (round(plain_gold, 2), crafts, plain, r.spell_id)
            else:
                key, plain_key = (score, crafts, r.spell_id), (plain, crafts, r.spell_id)
            found.append((key, plain_key, (key, r, crafts, lo, tools, requests)))
        return _pick(found)

    def _commit(self, prof, s, name, best):
        """Learn, get the tools and take the materials for the best recipe's crafts at skill s.
        Returns (cost, the step's (materials, from stock, own crafts used, extra, tools bought, from mail,
        tools mailed), whether it made something), or None when the materials ran out (the profession
        stalls)."""
        _key, r, crafts, lo, tools, requests = best
        step_cost, extra = Cost(), {}
        if r.spell_id not in self.learned and r.source == "trainer":
            self._train_in_window(prof, s, name)
        if r.spell_id not in self.learned:
            requests = lo[3] + requests  # quest hand-ins, taken with the crafts
            for i, q in lo[3]:
                extra[i] = extra.get(i, 0) + q
            step_cost += self._learn_now(r, lo, s, name)
        tool_cost, tool_extra, bought, tools_mailed = self._get_tools(tools, s, name)
        step_cost += tool_cost
        for i, q in tool_extra.items():
            extra[i] = extra.get(i, 0) + q
        before = _snapshot(self.pools)
        c = self.valuer.take_many(requests, self.pools, self.known, commit=True, learned=self.learned)
        if c is None:  # cannot happen: same requests, same order as the check above
            self.p.stalled[prof], self.p.stall_reasons[prof] = s, f"{name}: materials ran out at {s}"
            return None
        step_cost += c
        mats, from_stock, used_made, from_mail = _deltas(before, _snapshot(self.pools))
        made_something = False
        if r.output:
            item, per = r.output
            n = per * crafts
            opts = self.valuer.output_options(item, self.produced.get(item, 0))
            self.produced[item] = self.produced.get(item, 0) + n
            if self._should_hold(item, opts):
                self.held[item] = self.held.get(item, 0) + n
            else:
                self.pools.made[item] = self.pools.made.get(item, 0) + n
            made_something = True
        self.spent += step_cost
        return step_cost, (mats, from_stock, used_made, extra, bought, from_mail, tools_mailed), made_something

    def _merge_step(self, prof, s, r, crafts, step_cost, parts):
        """The skill point from s to s + 1 joins the last step when that crafts the same recipe up to s,
        or starts a new step. A rank trained at s ends the profession's step there: no step spans a training."""
        mats, from_stock, used_made, extra, bought, from_mail, tools_mailed = parts
        last = self.p.steps[-1] if self.p.steps else None
        trained_here = any(p == prof and sk == s for p, sk, _cap, _fee in self.p.ranks)
        if (last and last.profession == prof and last.spell_id == r.spell_id and last.skill_to == s
                and not trained_here):
            last.skill_to = s + 1
            last.crafts += crafts
            last.buffered += crafts * buffer_factor(crafts)
            last.cash += step_cost.cash
            last.economic += step_cost.economic
            for mine, new in ((last.materials, mats), (last.from_stock, from_stock), (last.used_made, used_made),
                              (last.extra, extra), (last.tools_bought, bought),
                              (last.from_mail, from_mail), (last.tools_mailed, tools_mailed)):
                for i, q in new.items():
                    mine[i] = mine.get(i, 0) + q
        else:
            self.p.steps.append(Step(prof, s, s + 1, r.spell_id, r.name, crafts, step_cost.cash, step_cost.economic,
                                     mats, from_stock, used_made, crafts * buffer_factor(crafts), extra, bought,
                                     from_mail, tools_mailed))

    def _after_step(self, prof, made_something):
        """Greens held for disenchanting are disenchanted once Enchanting can; new materials wake the
        professions stalled for lack of them."""
        made_something = self._release_held() or made_something
        for other in self.profs:
            if made_something and other != prof and other in self.soft_stalls:
                self.soft_stalls.discard(other)
                self.p.stalled.pop(other, None)
                self.p.stall_reasons.pop(other, None)

    def _finish(self) -> Plan:
        """The plan's totals, leftovers and what they sell for, once every step is planned."""
        p = self.p
        p.final_skill = dict(self.skill)
        p.skipped = sorted((k, v) for k, v in self.skipped.items() if k not in self.learned)
        p.crafted = dict(self.pools.crafted)
        p.other_crafts = {i: spell for (i, spell), n in self.pools.crafted_by.items()
                          if n > 1e-9 and (r := self.recipes.get(spell)) is not None and r.skill_line in self.fixed}
        p.held_for_de = {i: (n, de_skill_needed(self.gd.items[i].item_level)) for i, n in self.held.items()}
        p.bought, p.vendor_bought, p.farmed_bars = self.pools.bought, self.pools.vendor, self.pools.farmed
        p.farm = bars_to_ore(self.pools.farmed)
        p.used_stock = {i: n - self.pools.stock.get(i, 0) for i, n in self.stock.items.items()
                        if n - self.pools.stock.get(i, 0) > 1e-9}
        p.shared = {name: dict(items) for name, items in self.stock.shared.items()}
        p.used_mail = mail_used(p.shared, self.pools.mail)
        de_mats = set(p.de_materials)
        for item, n in list(self.pools.made.items()) + list(self.held.items()):
            if n < 1e-9:
                continue
            p.leftovers[item] = p.leftovers.get(item, 0) + n
            if item in self.held:
                continue  # kept for disenchanting, not sold
            if item in de_mats:
                p.leftover_value += n * self.valuer.owned_value(item)
                continue
            opts = self.valuer.output_options(item, 0)
            _reused, kept, sold = self._output_fate(item, n, opts, hold=False)  # as the score counts them
            if kept:
                p.kept_greens[item] = kept  # for another character's Enchanting: worth its materials
                p.leftover_value += kept * opts["de"]
            if sold:
                p.sale_proceeds += sale_value(self.valuer, self.gd, item, sold)
                p.vendor_back += sold * self.valuer.vendor_price(item)
        p.cash_total = self.spent.cash
        # crafts sold count at their vendor price only: what the AH pays on top never chooses the route
        p.economic_total = self.spent.economic - p.vendor_back - p.leftover_value
        return p


def _pick(found):
    """The best of _best_recipe's candidates, (key, key without the vendor credit, pick), or None: the lowest key among
    those whose skill-up chance is not lower than that of the best pick without the vendor credit. Vendor money may
    change which craft levels a point, but never pulls in one that needs more crafts for it (#97)."""
    if not found:
        return None
    crafts = min(found, key=lambda f: f[1])[2][2]
    return min((f for f in found if f[2][2] <= crafts + 1e-9), key=lambda f: f[0])[2]


def _snapshot(pools) -> dict:
    return {k: dict(getattr(pools, k)) for k in ("stock", "made", "bought", "vendor", "farmed", "mail")}


def _deltas(before: dict, after: dict):
    """What one step took: (materials from outside, the bank part of them, own crafts used, the part mailed
    by your other characters)."""
    def drop(k):  # amount that left pool k
        return {i: q - after[k].get(i, 0) for i, q in before[k].items() if q - after[k].get(i, 0) > 1e-9}

    def gain(k):  # amount added to pool k
        return {i: q - before[k].get(i, 0) for i, q in after[k].items() if q - before[k].get(i, 0) > 1e-9}

    from_stock, from_mail = drop("stock"), drop("mail")
    mats = dict(from_stock)
    for i, q in from_mail.items():
        mats[i] = mats.get(i, 0) + q
    for k in ("bought", "vendor", "farmed"):
        for i, q in gain(k).items():
            mats[i] = mats.get(i, 0) + q
    return mats, from_stock, drop("made"), from_mail


def sale_value(valuer, gd, item: int, n: float) -> float:
    """Selling n crafted items: on the AH up to the sale limit when the AH pays well above a vendor
    (`Valuer.ah_price`), the rest to a vendor. What is listed today doesn't cap it (#62)."""
    vendor = valuer.vendor_price(item)
    ah = valuer.ah_price(item)
    if ah is None:
        return n * vendor
    cap = min(n, valuer.sale_limit(item))
    return cap * ah + (n - cap) * vendor
