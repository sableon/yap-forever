"""Trips away from home: rank trainers in set towns, vendor patterns, the Favor vendor.

Trainer recipes are not trips (every trainer teaches the same list), nor are the ranks below 225
(Expert and Journeyman trainers are in the main cities: `city_ranks` lists those stops), nor AH
patterns (they come by mail).
"""
from dataclasses import dataclass

from yap_forever.gamedata import PROFESSIONS

REMOTE_RANK = 225  # ranks to 225 (Artisan) and 300 (Master) are trained in set towns
MAX_TRIP_ALTS = 3


@dataclass(frozen=True)
class Trip:
    skill: int
    profession: int
    kind: str  # "rank", "vendor" or "favor" (and "city" from city_ranks: a rank trained in a capital)
    what: str
    spell: int | None = None
    cost: float = 0
    cap: int = 0  # the skill cap a rank stop trains to


def trips(plan, gd) -> list["Trip"]:
    out = [Trip(s, prof, "rank", f"{PROFESSIONS.get(prof, prof)} rank to {cap}", None, fee, cap)
           for prof, s, cap, fee in plan.ranks if cap >= REMOTE_RANK]
    for prof, s, spell, how in plan.learn_log:
        if how in ("vendor", "favor"):
            r = gd.recipes.get(spell)
            name = r.name if r else str(spell)
            cost = gd.vendor_prices.get(r.scroll_item, 0) if r and how == "vendor" and r.scroll_item else 0
            out.append(Trip(s, prof, how, name, spell, cost))
    return sorted(out, key=lambda t: (t.skill, t.kind != "vendor" and t.kind != "favor", t.profession))


def city_ranks(plan) -> list["Trip"]:
    """The ranks below REMOTE_RANK, trained at any trainer of that rank in a capital: stops, not trips."""
    return [Trip(s, prof, "city", f"{PROFESSIONS.get(prof, prof)} rank to {cap}", None, fee, cap)
            for prof, s, cap, fee in plan.ranks if cap < REMOTE_RANK]


def trip_alternatives(base, inputs, mode) -> dict[int, float | None]:
    """For vendor and Favor trips (the costliest few): what the route costs more without that recipe,
    in the route's own measure; None when the targets can't be reached without it.
    inputs: the plan.PlanInputs the route was planned from."""
    from yap_forever.plan import plan_route  # plan imports this module

    measure = (lambda p: p.cash_total) if mode == "gold" else (lambda p: p.economic_total)
    goals = set(inputs.craft_once.values())  # the goal recipe can't be skipped
    picks = sorted((t for t in trips(base, inputs.gd) if t.spell is not None and t.spell not in goals),
                   key=lambda t: -t.cost)[:MAX_TRIP_ALTS]
    out: dict[int, float | None] = {}
    for t in picks:
        alt = plan_route(inputs, mode, exclude=frozenset({t.spell}))
        reached = all(alt.final_skill.get(p, 0) >= base.final_skill.get(p, 0) for p in inputs.caps)
        out[t.spell] = measure(alt) - measure(base) if reached else None
    return out
