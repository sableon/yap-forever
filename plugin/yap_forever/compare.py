"""The least-gold and least-total-value routes side by side, with what each asks of your time."""
import math

from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import gold
from yap_forever.trips import trips

ROUTE_NAMES = {"gold": "Least gold", "value": "Least total value"}
THIN_SHARE = 0.5  # buying at least half of what is listed moves the price


def _to_sell(plan, gd, market) -> str:
    items = {i: n for i, n in plan.leftovers.items() if n >= 1 and market.net_sell(i) and i not in plan.held_for_de
             and i not in plan.kept_greens}
    if not items:
        return "nothing"
    count = sum(math.floor(n) for n in items.values())
    listings = sum(math.ceil(math.floor(n) / (gd.items[i].stack if i in gd.items else 1)) for i, n in items.items())
    return f"{count} items in {listings} listings"


def _thin(plan, gd, market) -> str:
    names = []
    for i, n in sorted(plan.bought.items()):
        depth = market.depth(i)
        if depth and n >= THIN_SHARE * depth:
            names.append(f"{gd.name(i)} (buys {math.ceil(n)} of {depth})")
    for i, n in sorted(plan.leftovers.items()):
        depth = market.depth(i)
        if market.net_sell(i) and i not in plan.held_for_de and n > depth:
            names.append(f"{gd.name(i)} (sells {math.floor(n)}, {depth} listed)")
    return "; ".join(names) or "none"


def reaches(plan, caps: dict) -> bool:
    return all(plan.final_skill.get(x, 0) >= c for x, c in caps.items())


def settle_routes(candidates: list, caps: dict) -> tuple[dict, bool]:
    """Among candidate routes that reach every target (or, if none does, those that get furthest):
    least gold is the lowest gold out of pocket, least total value the lowest total value. The
    planner chooses one skill point at a time, so no single mode is sure to win its own measure."""
    pool = [p for p in candidates if reaches(p, caps)]
    if not pool:
        best = max(sum(p.final_skill.values()) for p in candidates)
        pool = [p for p in candidates if sum(p.final_skill.values()) == best]
    g = min(pool, key=lambda p: (p.cash_total, p.economic_total))
    v = min(pool, key=lambda p: (p.economic_total, p.cash_total))
    return {"gold": g, "value": v}, g is v


def compare(routes: dict, gd, market, stock, mailbox_trips: dict | None = None, same: bool = False) -> str:
    modes = [m for m in ROUTE_NAMES if m in routes]

    def row(label, f):
        return f"| {label} | " + " | ".join(f(routes[m], m) for m in modes) + " |"

    def reached(p, _m):
        return ", ".join(f"{PROFESSIONS.get(x, x)} {s}" for x, s in p.final_skill.items()) or "—"

    def away(p, _m):
        return str(len(trips(p, gd))) if trips(p, gd) else "none"

    def mail(_p, m):
        return str(mailbox_trips[m]) if mailbox_trips and m in mailbox_trips else "—"

    return "\n".join([
        "| | " + " | ".join(ROUTE_NAMES[m] for m in modes) + " |",
        "|---|" + "---:|" * len(modes),
        row("Gold out of pocket", lambda p, _m: gold(p.cash_total)),
        row("Total value", lambda p, _m: gold(p.economic_total)),
        row("Reached", reached),
        row("To sell", lambda p, _m: _to_sell(p, gd, market)),
        row("Mailbox trips", mail),
        row("Trips away", away),
        row("Thin markets", lambda p, _m: _thin(p, gd, market)),
    ] + (["", "The least-total-value route also spends the least gold, so both guides are the same route."]
         if same else []))
