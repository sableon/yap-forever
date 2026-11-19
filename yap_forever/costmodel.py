"""What things cost: skill-up chance, reagents from stock / farming / vendor / AH / crafting."""
import math
import tomllib
from dataclasses import dataclass, field

from yap_forever.config import STATIC_DIR
from yap_forever.disenchant import de_skill_needed, de_yield

AH_UNIT_CAP = 5  # AH sales of one crafted item counted at the lowest price; quest items exempt
VENDOR_TOOLS = {5956}  # Blacksmith Hammer

with open(STATIC_DIR / "ore.toml", "rb") as _f:
    ORE = tomllib.load(_f)
ORES = {int(k): (v[0], v[1]) for k, v in ORE["ore"].items()}  # ore -> (name, mining skill)
STONES = {int(k): (v[0], v[1]) for k, v in ORE.get("stone", {}).items()}  # stone -> (name, mining skill)
BARS = {int(k): (v[0], {int(a): b for a, b in v[1].items()}, v[2], v[3]) for k, v in ORE["bars"].items()}


MODES = ("gold", "value")


def craft_margin(skill: int) -> float:
    """Craft an intermediate only when it costs less than this share of buying it: 0.90 at skill 1
    (early materials cost tens of silver, small savings aren't worth a craft), 0.95 at 300."""
    return 0.90 + 0.05 * (min(max(skill, 1), 300) - 1) / 299


OVERTIME_READINGS = ("relative", "points")
OVERTIME_STEP = 0.04  # Working Overtime: per rank, on every tradeskill (rank 0-5)


def skillup_chance(skill: int, t: tuple[int, int, int, int], overtime: int = 0,
                   reading: str = "relative") -> float:
    """Chance of a skill-up for one craft. overtime = Working Overtime rank; `reading` says how its
    4% per rank applies: "relative" scales the base chance, "points" adds to it. Both cap at 1;
    a craft that can't skill up (grey, or below orange) stays at 0."""
    if reading not in OVERTIME_READINGS:
        raise ValueError(f"unknown Working Overtime reading {reading!r}: "
                         f"use one of {', '.join(OVERTIME_READINGS)}")
    orange, yellow, _green, grey = t
    if skill < orange or skill >= grey:
        return 0.0
    if skill < yellow:
        return 1.0
    p = (grey - skill) / (grey - yellow)
    if not overtime or p <= 0:
        return p
    if reading == "points":
        return min(1.0, p + OVERTIME_STEP * overtime)
    return min(1.0, p * (1 + OVERTIME_STEP * overtime))


def money(c: float) -> str:
    c = int(round(c))
    sign = "-" if c < 0 else ""
    c = abs(c)
    g, s, cp = c // 10000, c // 100 % 100, c % 100
    return f"{sign}{g}g {s}s {cp}c" if g else f"{sign}{s}s {cp}c"


@dataclass
class Cost:
    cash: float = 0
    economic: float = 0
    score: float | None = None  # for choosing recipes: also values made items at what they're worth

    def __post_init__(self):
        if self.score is None:
            self.score = self.economic

    def __add__(self, o):
        return Cost(self.cash + o.cash, self.economic + o.economic, self.score + o.score)


@dataclass
class Pools:
    stock: dict[int, float]
    made: dict[int, float] = field(default_factory=dict)  # crafted or disenchanted, not yet used
    bought: dict[int, float] = field(default_factory=dict)  # from the AH
    vendor: dict[int, float] = field(default_factory=dict)
    farmed: dict[int, float] = field(default_factory=dict)  # bars to mine and smelt
    crafted: dict[int, float] = field(default_factory=dict)  # intermediates crafted on the way
    tools: set[int] = field(default_factory=set)

    @classmethod
    def from_stock(cls, stock) -> "Pools":
        return cls(stock={k: float(v) for k, v in stock.items.items() if v})


class Valuer:
    def __init__(self, market, gd, stock, mode: str = "value"):
        """mode "value": choose by total value (owned items at what they'd sell for);
        "gold": choose by gold spent first (owned items free), total value second."""
        if mode not in MODES:
            raise ValueError(f"route mode must be one of {', '.join(MODES)}, not {mode!r}")
        self.market, self.gd, self.stock, self.mode = market, gd, stock, mode

    # --- values ------------------------------------------------------------
    def owned_value(self, item: int) -> float:
        info = self.gd.items.get(item)
        return max(self.market.net_sell(item) or 0, info.sell_price if info else 0)

    def output_options(self, item: int, n_already: float) -> dict[str, float]:
        info = self.gd.items.get(item)
        opts = {"vendor": info.sell_price if info else 0}
        ns = self.market.net_sell(item)
        if ns and n_already < min(self.sale_limit(item), self.market.depth(item)):
            opts["ah"] = ns
        if info and de_skill_needed(info.item_level) <= 225:
            dv = sum(n * self.material_value(m) for m, n in de_yield(info).items())
            if dv:
                opts["de"] = dv
        return opts

    def sale_limit(self, item: int) -> float:
        """How many of a crafted item the AH takes: 5, or the quest-item setting for quest items.

        Callers also cap this at what is listed today (`market.depth`): more would not sell at that price."""
        if item in self.gd.quest_items:
            limit = self.stock.quest_item_sales
            return math.inf if limit is None else limit
        return AH_UNIT_CAP

    def material_value(self, item: int) -> float:
        """A material you'd otherwise buy: worth at least its AH buy price."""
        return max(self.owned_value(item), self.market.min_price(item) or 0)

    def output_value(self, item: int, n_already: float) -> int:
        return int(max(self.output_options(item, n_already).values()))

    def buy_option(self, item: int, qty: float, already: float) -> tuple[str, float] | None:
        """Cheapest of vendor and AH for qty more units, given `already` bought on the AH."""
        opts = []
        if item in self.gd.vendor_prices:
            opts.append(("vendor", self.gd.vendor_prices[item] * qty))
        hi = self.market.buy_cost(item, math.ceil(already + qty - 1e-9))
        lo = self.market.buy_cost(item, math.ceil(already - 1e-9))
        if hi is not None and lo is not None:
            opts.append(("ah", hi - lo))
        return min(opts, key=lambda o: o[1]) if opts else None

    def farmable(self, item: int) -> bool:
        mining = max(self.stock.mining, self.stock.mining_goal)
        if item in STONES:
            return STONES[item][1] <= mining
        return item in BARS and BARS[item][2] <= mining

    # --- taking reagents -----------------------------------------------------
    def take(self, item: int, qty: float, pools: Pools, skills: dict[int, int],
             commit: bool = True, learned: set[int] | None = None) -> Cost | None:
        return self.take_many([(item, qty)], pools, skills, commit, learned)

    def take_many(self, requests: list[tuple[int, float]], pools: Pools, skills: dict[int, int],
                  commit: bool = True, learned: set[int] | None = None) -> Cost | None:
        """Take several items in order as one transaction; rolled back unless committed."""
        log: list[tuple[dict, int, float]] = []

        def move(d, k, delta):
            d[k] = d.get(k, 0) + delta
            log.append((d, k, delta))

        total: Cost | None = Cost()
        for item, qty in requests:
            c = self._take(item, qty, pools, skills, move, 0, learned or set())
            if c is None:
                total = None
                break
            total = total + c
        if not commit or total is None:
            for d, k, delta in reversed(log):
                d[k] -= delta
                if abs(d[k]) < 1e-9:
                    del d[k]
        return total

    def _take(self, item, qty, pools, skills, move, depth, learned) -> Cost | None:
        cost, need = Cost(), qty
        for pool, made in ((pools.made, True), (pools.stock, False)):
            have = pool.get(item, 0)
            n = min(have, need)
            if n > 1e-9:
                move(pool, item, -n)
                v = self.owned_value(item)
                cost = cost + Cost(0, 0 if made else n * v, n * v)
                need -= n
        if need <= 1e-9:
            return cost
        if self.farmable(item):
            if item in BARS:  # smelt what the bank's ore, coal and bars allow before mining more
                n = min(need, self._smeltable(item, pools))
                if n > 1e-9:
                    cost = cost + self._smelt_owned(item, n, pools, move)
                    need -= n
                if need <= 1e-9:
                    return cost
            move(pools.farmed, item, need)
            extra = self._smelt_extras(item, need, pools, move) if item in BARS else Cost()
            return cost + extra + Cost(0, need * self.owned_value(item))
        buy = self.buy_option(item, need, pools.bought.get(item, 0))
        if buy and depth < 2:  # craft instead when that is cheaper by more than the margin
            log: list = []

            def trial_move(d, k, delta):
                d[k] = d.get(k, 0) + delta
                log.append((d, k, delta))

            trial = self._craft(item, need, pools, skills, trial_move, depth, learned)
            for d, k, delta in reversed(log):
                d[k] -= delta
                if abs(d[k]) < 1e-9:
                    del d[k]
            if trial is not None:
                made, recipe = trial
                measure = (lambda c: c.cash) if self.mode == "gold" else (lambda c: c.economic)
                if measure(made) < craft_margin(skills.get(recipe.skill_line, 0)) * buy[1] - 1e-9:
                    return cost + self._craft(item, need, pools, skills, move, depth, learned)[0]
        if buy:
            kind, price = buy
            move(pools.bought if kind == "ah" else pools.vendor, item, need)
            return cost + Cost(price, price)
        if depth < 2:
            crafted = self._craft(item, need, pools, skills, move, depth, learned)
            if crafted is not None:
                return cost + crafted[0]
        return None

    def _craft(self, item, need, pools, skills, move, depth, learned):
        """(cost, recipe) of crafting `need` of item with a known recipe and the tools at hand, or None."""
        held = set(pools.tools) | {i for i, n in pools.made.items() if n >= 1} | \
            {i for i, n in pools.stock.items() if n >= 1}
        for r in self.gd.recipes.values():
            if not r.output or r.output[0] != item:
                continue
            if r.source != "starter" and r.spell_id not in learned:
                continue
            if skills.get(r.skill_line, 0) < r.required_skill:
                continue
            if any(not any(self.gd.satisfies(t, cat) for t in held) for cat in r.tools):
                continue
            crafts = need / r.output[1]
            sub = Cost()
            for reagent, q in r.reagents.items():
                c = self._take(reagent, q * crafts, pools, skills, move, depth + 1, learned)
                if c is None:
                    sub = None
                    break
                sub = sub + c
            if sub is not None:
                move(pools.crafted, item, need)
                return sub, r
        return None

    def _owned(self, item: int, pools: Pools) -> float:
        return pools.made.get(item, 0) + pools.stock.get(item, 0)

    def _smeltable(self, bar: int, pools: Pools) -> float:
        """Bars that owned ore and bars could make (component bars smelted in turn). Coal and other
        vendor reagents don't limit it: they come from the bank first, then the vendor."""
        if bar not in BARS or not self.farmable(bar):
            return 0.0
        _name, reagents, _skill, per = BARS[bar]
        limits = [(self._owned(r, pools) + self._smeltable(r, pools)) * per / q
                  for r, q in reagents.items() if r in ORES or r in BARS]
        return min(limits) if limits else 0.0

    def _take_owned(self, item: int, qty: float, pools: Pools, move) -> Cost:
        """Take qty from made, then the bank, then smelt the rest from owned reagents."""
        cost = Cost()
        for pool, made in ((pools.made, True), (pools.stock, False)):
            n = min(pool.get(item, 0), qty)
            if n > 1e-9:
                move(pool, item, -n)
                v = self.owned_value(item)
                cost = cost + Cost(0, 0 if made else n * v, n * v)
                qty -= n
        if qty > 1e-9:
            cost = cost + self._smelt_owned(item, qty, pools, move)
        return cost

    def _smelt_owned(self, bar: int, n: float, pools: Pools, move) -> Cost:
        _name, reagents, _skill, per = BARS[bar]
        cost = Cost()
        for r, q in reagents.items():
            if r in ORES or r in BARS:
                cost = cost + self._take_owned(r, q * n / per, pools, move)
            else:
                cost = cost + self._vendor_reagent(r, q * n / per, pools, move)
        return cost

    def _vendor_reagent(self, item: int, qty: float, pools: Pools, move) -> Cost:
        """Coal and the like: from the bank first (no cash, counted at its value), the rest from a vendor."""
        cost = Cost()
        for pool, made in ((pools.made, True), (pools.stock, False)):
            n = min(pool.get(item, 0), qty)
            if n > 1e-9:
                move(pool, item, -n)
                v = self.owned_value(item)
                cost = cost + Cost(0, 0 if made else n * v, n * v)
                qty -= n
        if qty <= 1e-9:
            return cost
        unit = self.gd.vendor_prices.get(item, self.gd.items[item].buy_price if item in self.gd.items else 0)
        move(pools.vendor, item, qty)
        return cost + Cost(unit * qty, unit * qty)

    def _smelt_extras(self, bar: int, n: float, pools: Pools, move) -> Cost:
        """Non-ore smelting reagents (coal) when farming n bars: bank first, then vendor."""
        _name, reagents, _skill, per = BARS[bar]
        cost = Cost()
        for r, q in reagents.items():
            if r in ORES:
                continue
            if r in BARS:
                cost = cost + self._smelt_extras(r, q * n / per, pools, move)
            else:
                cost = cost + self._vendor_reagent(r, q * n / per, pools, move)
        return cost


def bars_to_ore(farmed: dict[int, float]) -> dict[int, int]:
    """Ore and stone to mine for what was farmed (bronze resolved to copper and tin)."""
    ore: dict[int, float] = {}

    def add(bar, n):
        _name, reagents, _skill, per = BARS[bar]
        for r, q in reagents.items():
            if r in ORES:
                ore[r] = ore.get(r, 0) + q * n / per
            elif r in BARS:
                add(r, q * n / per)

    for bar, n in farmed.items():
        if bar in STONES:
            ore[bar] = ore.get(bar, 0) + n
        else:
            add(bar, n)
    return {k: math.ceil(v - 1e-9) for k, v in ore.items()}
