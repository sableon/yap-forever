"""Shopping list, mailbox trips and what to bring to a remote trainer.

Ported from the old scripts/shopping.py, working on Plan steps. Rows are counted in whole crafts with
the buffer on yellow and green steps (planner.step_factor), so every material is a whole number of
crafts' worth: nothing is left over that is too little for another craft.
"""
import copy
import dataclasses
import math

from yap_forever.disenchant import ESSENCE_PAIRS
from yap_forever.guide import gold
from yap_forever.planner import DISENCHANT, step_factor
from yap_forever.shared import allocate
from yap_forever.trips import AS_NEEDED, ONE_GO, stretch_end, visits

CRAFT_ROOM = 10  # slots a trip leaves free for crafts and intermediates
BRING_POINTS = 25  # without a bag count, bring enough for this many points (or to the stage end)


def stacks(gd, items) -> dict[int, int]:
    items = set(items) | {ESSENCE_PAIRS[i] for i in items if i in ESSENCE_PAIRS}  # packed essences
    return {i: (gd.items[i].stack if i in gd.items else 1) for i in items}


def slots(counts: dict, stack: dict) -> int:
    return sum(math.ceil(q / stack.get(i, 1) - 1e-9) for i, q in counts.items() if q > 1e-9)


def pack(counts: dict, stack: dict) -> dict:
    """What you carry: lesser essences packed 3 -> 1 greater as far as it saves bag slots (packing
    all of them on a tie); a greater essence the route needs shares the packed stacks."""
    out = {i: q for i, q in counts.items() if q > 1e-9}
    for lesser, greater in ESSENCE_PAIRS.items():
        whole = math.ceil(out.get(lesser, 0) - 1e-6)
        if whole < 3:
            continue
        had = out.get(greater, 0)

        def cost(k):
            return slots({lesser: whole - 3 * k, greater: had + k}, stack)  # noqa: B023 (called in this loop pass only)

        k = min(range(whole // 3 + 1), key=lambda k: (cost(k), -k))
        if k:
            out[greater] = had + k
            out[lesser] = whole - 3 * k
            if not out[lesser]:
                del out[lesser]
    return out


def carried_slots(counts: dict, stack: dict) -> int:
    """Bag slots for carrying `counts`, essences packed."""
    return slots(pack(counts, stack), stack)


def reagent_items(gd) -> set[int]:
    """Items a reagent bag holds: any item a loaded recipe uses as a reagent, or trade goods (ItemSparse
    class 7), crafted intermediates and disenchant materials included. Gear (class 2 weapons, 4 armor),
    patterns (class 9) and tools never go in it."""
    out = {i for r in gd.recipes.values() for i in r.reagents}
    out |= {i for i, it in gd.items.items() if it.class_id == 7}
    never = {i for i, it in gd.items.items() if it.class_id in (2, 4, 9)}
    return out - never - set(gd.item_tool_category)


def _split_slots(counts: dict, stack: dict, reagents, reagent_slots: int) -> tuple[int, int]:
    """(normal slots, reagent bag slots) used by `counts` as they are: reagent stacks fill the reagent
    bag first, what does not fit and every other stack take normal slots."""
    reagents = set(reagents or ()) | {ESSENCE_PAIRS[i] for i in (reagents or ()) if i in ESSENCE_PAIRS}  # packed essences
    mine = slots({i: q for i, q in counts.items() if i in reagents}, stack)
    rest = slots({i: q for i, q in counts.items() if i not in reagents}, stack)
    in_bag = min(mine, max(reagent_slots, 0))
    return rest + mine - in_bag, in_bag


def carried_split(counts: dict, stack: dict, reagents, reagent_slots: int) -> tuple[int, int]:
    """(normal slots, reagent bag slots) for carrying `counts`, essences packed."""
    return _split_slots(pack(counts, stack), stack, reagents, reagent_slots)


def carried_slots_split(counts: dict, stack: dict, reagents, reagent_slots: int) -> int:
    """Normal slots for carrying `counts` after the reagent bag takes reagent stacks first (essences
    packed; packed essences count as reagents). Without a reagent bag it is `carried_slots`."""
    return carried_split(counts, stack, reagents, reagent_slots)[0]


def slots_text(split: tuple[int, int]) -> str:
    """'4 bag slots', or '1 bag slot + 3 reagent bag slots' when the reagent bag holds some."""
    normal, bag = split
    parts = [f"{n} {word}slot{'s' if n != 1 else ''}"
             for n, word, show in ((normal, "bag ", normal or not bag), (bag, "reagent bag ", bag)) if show]
    return " + ".join(parts)


def pack_note(gd, counts: dict, stack: dict, unpack: str) -> str:
    """'to save slots, pack 90 Lesser X into 30 Greater X (3 to 1) and unpack ...', or ''."""
    packed = pack(counts, stack)
    parts = []
    for lesser, greater in ESSENCE_PAIRS.items():
        k = packed.get(greater, 0) - counts.get(greater, 0)
        if k > 1e-9:
            k = round(k)
            parts.append(f"{3 * k} {gd.name(lesser)} into {k} {gd.name(greater)}")
    return f"to save slots, pack {', '.join(parts)} (3 to 1) and unpack {unpack}" if parts else ""


def batch_size(per_craft: dict, output, stack: dict, free: int, reagents=None, reagent_slots: int = 0) -> int:
    """Most crafts whose mats (from the mail) and products (until sold) fit in `free` normal slots at
    once; the reagent bag (`reagent_slots`) takes reagent stacks first."""
    best = 0
    for k in range(1, 1000):
        peak = max(_split_slots({i: q * (k - t) for i, q in per_craft.items()}
                                | ({output[0]: output[1] * t} if output else {}), stack, reagents, reagent_slots)[0]
                   for t in range(k + 1))
        if peak > free:
            return best
        best = k
    return best


def _sum(dicts) -> dict:
    out: dict = {}
    for d in dicts:
        for i, q in d.items():
            out[i] = out.get(i, 0) + q
    return out


def merged_steps(plan, gd, split: tuple[int, int] | None = None) -> list[tuple]:
    """(step, parts): runs of one recipe over consecutive skill points as one step, so the buffer is
    rounded up once per run, not once per skill point. split: (profession, skill): no run of that profession
    crosses that skill (a trip's bring list starts there)."""
    out: list[tuple] = []
    latest: dict[int, int] = {}  # profession -> index of its latest entry (professions interleave)
    for st in plan.steps:
        if st.spell_id == DISENCHANT or st.spell_id not in gd.recipes or not (st.skill_from < st.skill_to or st.crafts > 0):
            continue
        at = latest.get(st.profession)
        last = out[at] if at is not None else None
        if (last and st.skill_from < st.skill_to and last[0].skill_from < last[0].skill_to
                and last[0].spell_id == st.spell_id and last[0].profession == st.profession
                and last[0].skill_to == st.skill_from
                and not (split and split[0] == st.profession and last[0].skill_from < split[1] <= st.skill_from)):
            parts = last[1] + [st]
            out[at] = (dataclasses.replace(
                last[0], skill_to=st.skill_to, crafts=sum(p.crafts for p in parts),
                buffered=sum(p.crafts * step_factor(p) for p in parts),
                cash=sum(p.cash for p in parts), economic=sum(p.economic for p in parts),
                materials=_sum(p.materials for p in parts), from_stock=_sum(p.from_stock for p in parts),
                used_made=_sum(p.used_made for p in parts), extra=_sum(p.extra for p in parts),
                tools_bought=_sum(p.tools_bought for p in parts), from_mail=_sum(p.from_mail for p in parts),
                tools_mailed=_sum(p.tools_mailed for p in parts)), parts)
        else:
            latest[st.profession] = len(out)
            out.append((st, [st]))
    return out


def route_rows(plan, gd, split: tuple[int, int] | None = None) -> list[dict]:
    """Rows in whole crafts: n crafts (buffer included) take n times what one craft takes, so no count
    leaves a remainder too small for another craft. Your own crafts from earlier rows are used first;
    intermediates still missing are crafted in whole batches at the first row that needs or makes them.
    need: what to bring (bank, mail or vendor); earlier: your own crafts (from any row) or disenchants used;
    here: intermediates crafted on the spot; more: extra crafts of the row's own recipe for later rows.
    split: see merged_steps."""
    merged = merged_steps(plan, gd, split)
    steps = [st for st, _parts in merged]
    makes = {r.output[0]: r for r in gd.recipes.values() if r.output}
    craftable = set(plan.crafted) | {gd.recipes[st.spell_id].output[0] for st in steps if gd.recipes[st.spell_id].output}
    pool: dict[int, float] = {}  # your own crafts on hand
    rows, missing = [], {}  # missing: intermediate -> [count, index of the first row needing it]
    for st, parts in merged:
        r, k = gd.recipes[st.spell_id], step_factor(st)
        row = {"st": st, "parts": parts, "n": math.ceil(st.crafts * k - 1e-9), "more": 0, "need": {}, "here": {},
               "earlier": {}, "tools": {i: math.ceil(q - 1e-6) for i, q in _sum([st.tools_bought, st.tools_mailed]).items()}}
        demand = {i: q * row["n"] for i, q in r.reagents.items()}  # whole crafts, buffered
        planned = {i: q * st.crafts for i, q in r.reagents.items()}  # what the planner took per craft
        for i, q in st.extra.items():  # taken once: quest hand-ins, a crafted tool's materials
            demand[i] = demand.get(i, 0) + math.ceil(q - 1e-6)
            planned[i] = planned.get(i, 0) + q
        for i, d in demand.items():
            if i in makes and i in craftable:
                own = min(d, pool.get(i, 0))
            else:  # disenchanted reagents: the planner's expected count, buffered
                own = min(d, math.ceil(st.used_made.get(i, 0) * k - 1e-6))
            if own:
                row["earlier"][i] = own
                if i in pool:
                    pool[i] -= own
            rest = d - own
            planner_made = planned[i] - st.materials.get(i, 0) - st.used_made.get(i, 0)
            if rest <= 0:
                continue
            if i in makes and i in craftable and not (st.materials.get(i, 0) > 1e-6 and planner_made <= 0.01):
                m = missing.setdefault(i, [0, len(rows)])
                m[0] += rest
                row["earlier"][i] = row["earlier"].get(i, 0) + rest  # yours: crafted in the batch below
            else:
                row["need"][i] = row["need"].get(i, 0) + rest
        for i, q in row["tools"].items():  # bought or mailed, never crafted here
            row["need"][i] = row["need"].get(i, 0) + q
        if r.output:
            pool[r.output[0]] = pool.get(r.output[0], 0) + row["n"] * r.output[1]
        rows.append(row)
    for _ in range(4):  # nested intermediates (an intermediate of an intermediate)
        nested: dict[int, list] = {}
        for i, (count, at) in sorted(missing.items()):
            maker = makes[i]
            first = next((x for x in rows[:at] if gd.recipes[x["st"].spell_id].output == maker.output), rows[at])
            crafts = math.ceil(count / maker.output[1] - 1e-9)
            if first is not rows[at]:
                first["more"] += crafts  # the row that makes i as its own step makes these too
            else:
                first["here"][i] = first["here"].get(i, 0) + count
            for j, q in maker.reagents.items():
                if j in makes and j in craftable:
                    m = nested.setdefault(j, [0, rows.index(first)])
                    m[0] += q * crafts
                else:
                    first["need"][j] = first["need"].get(j, 0) + q * crafts
        if not nested:
            break
        missing = nested
    return rows


def group_trips(rows, cap: int, stack: dict, reagents=None, reagent_slots: int = 0) -> list[list[dict]]:
    """Consecutive rows whose mats fit in `cap` normal slots, after the reagent bag takes its share
    of reagent stacks: one mailbox trip each."""
    def used(counts):
        return carried_slots_split(counts, stack, reagents, reagent_slots)

    trips, need = [[]], {}
    for r in rows:
        trial = dict(need)
        for i, q in r["need"].items():
            trial[i] = trial.get(i, 0) + q
        if trips[-1] and used(trial) > max(cap, used(need)):  # rows adding no stacks stay
            trips.append([])
            trial = dict(r["need"])
        trips[-1].append(r)
        need = trial
    return trips if rows else []


def _bank(plan) -> dict[int, float]:
    """What the route takes from the bank: the planner's unbuffered use; the buffer on top is bought."""
    out: dict[int, float] = {}
    for st in plan.steps:
        for i, q in st.from_stock.items():
            out[i] = out.get(i, 0) + q
    return {i: math.ceil(q - 1e-6) for i, q in out.items()}  # you own whole items


MAIL_FROM = "from:"  # a source "from:<Name>": mailed by another of your characters (not "mail", bought on the AH)


def from_character(src: str) -> str | None:
    """The character a source names, or None for bank, mail (AH) and vendor."""
    return src[len(MAIL_FROM):] if src.startswith(MAIL_FROM) else None


def _mail(plan, whole_pool: bool = False) -> dict[int, list[list]]:
    """What your other characters can mail you: item -> [[name, count]] in name order.
    The planner's own use of it; with whole_pool, everything they hold of the items the planner drew from
    them (the buffer comes from there while it lasts, as from the bank). An item the planner did not take
    by mail is never named, whatever the others hold."""
    drawn = set(plan.used_mail)
    for st in plan.steps:
        drawn |= set(st.from_mail) | set(st.tools_mailed)
    if whole_pool:
        want = {i: sum(held.get(i, 0) for held in plan.shared.values()) for i in drawn}
    else:
        want = {}
        for st in plan.steps:
            for d in (st.from_mail, st.tools_mailed):
                for i, q in d.items():
                    want[i] = want.get(i, 0) + q
        want = {i: math.ceil(q - 1e-6) for i, q in want.items()}
    return {i: [[name, n] for name, n in allocate(plan.shared, i, int(n))] for i, n in want.items()}


def _split(rows, plan, gd=None, left=None, mail=None) -> dict[tuple[int, str], int]:
    """(item, source) -> whole count over these rows; source: bank, from:<Name> (mailed by another of your
    characters), mail (bought on the AH) or vendor. Farmed bars are left out (the keep list covers mining).
    left, mail: what the bank and your other characters still hold, shared across trips so each is used once."""
    left = _bank(plan) if left is None else left
    mail = _mail(plan) if mail is None else mail
    out: dict[tuple[int, str], int] = {}
    for r in rows:
        for i, q in r["need"].items():
            if i in plan.farmed_bars:
                continue
            bank = min(q, left.get(i, 0))
            left[i] = left.get(i, 0) - bank
            if bank > 1e-6:
                out[(i, "bank")] = out.get((i, "bank"), 0) + math.ceil(bank - 1e-6)
            rest = q - bank
            for source in mail.get(i, ()):  # name order
                if rest <= 1e-6:
                    break
                n = min(rest, source[1])
                if n <= 1e-6:  # this character has nothing more to mail
                    continue
                source[1] -= n
                rest -= n
                key = (i, MAIL_FROM + source[0])
                out[key] = out.get(key, 0) + math.ceil(n - 1e-6)
            vendor = i not in plan.bought and (i in plan.vendor_bought or (gd is not None and i in gd.vendor_prices))
            if rest > 1e-6:
                key = (i, "vendor" if vendor else "mail")
                out[key] = out.get(key, 0) + math.ceil(rest - 1e-6)
    return out


def mailed(plan, gd, stock) -> dict[int, list[tuple[str, int]]]:
    """item -> (character, count): what your other characters are asked to mail, as the shopping list and
    the mailbox trips count it (whole crafts, buffer included). A mailed pattern, which no row needs, is
    named as the plan took it."""
    rows = route_rows(plan, gd)
    split = _split(rows, plan, gd, {i: float(n) for i, n in stock.items.items()}, _mail(plan, whole_pool=True))
    out: dict[int, list[tuple[str, int]]] = {}
    for (i, src), n in sorted(split.items()):
        who = from_character(src)
        if who is not None:
            out.setdefault(i, []).append((who, n))
    needed = {i for r in rows for i in r["need"]}
    for i, sources in plan.used_mail.items():
        if i not in out and i not in needed:
            out[i] = list(sources)
    return out


YOURS = "yours"  # a bring-list source: your own crafts and disenchants from earlier on the route


def _made_earlier(rows, gd) -> dict[int, int]:
    """item -> how many of your own crafts and disenchants these rows use that they don't make themselves: made
    earlier on the route, by either profession."""
    used = _sum(r["earlier"] for r in rows)
    made = _sum([r["here"] for r in rows] + [{out[0]: (r["n"] + r["more"]) * out[1]} for r in rows
                                             if (out := gd.recipes[r["st"].spell_id].output)])
    return {i: math.ceil(q - made.get(i, 0) - 1e-6) for i, q in sorted(used.items()) if q - made.get(i, 0) > 1e-6}


def _bring_rows(plan, gd, trip, bag_slots, owned, reagent_slots, reagents, start_skills, trainer_trips):
    """(rows the trip's bring list covers, what the bank and the mail hold when it starts): see bring_list. With
    one go, a run of one recipe that crosses the trip's skill is split there, so its rest is brought too."""
    every = route_rows(plan, gd, (trip.profession, trip.skill) if trainer_trips == ONE_GO else None)
    at = next((k for k, r in enumerate(every)
               if r["st"].profession == trip.profession and r["st"].skill_from >= trip.skill), len(every))
    rows = [r for r in every[at:] if r["st"].profession == trip.profession]
    left = {i: float(n) for i, n in owned.items()} if owned is not None else _bank(plan)
    mail = _mail(plan, whole_pool=owned is not None)
    if not rows:
        return rows, left, mail
    _split(every[:at], plan, gd, left, mail)  # the bank and the mail the rows before the trip use
    if trainer_trips == ONE_GO:  # the whole stretch, whatever the bags hold (the bag warning says if it fits)
        end = stretch_end(plan, trip.profession, trip.skill)
        return [r for r in rows if r["st"].skill_to <= end] or rows[:1], left, mail
    later = [s for p, s, _c, _f in plan.ranks if p == trip.profession and s > trip.skill]
    if start_skills is not None:
        later += [v.skill for v in visits(plan, gd, start_skills)
                  if v.profession == trip.profession and v.kind != "rank" and v.skill > trip.skill]
    if later:  # the next rank trip, or the next trip back for recipes, brings its own
        rows = [r for r in rows if r["st"].skill_to <= min(later)] or rows[:1]
    if bag_slots:
        items = {i for r in rows for i in r["need"]}
        rows = group_trips(rows, bag_slots - CRAFT_ROOM, stacks(gd, items),
                           reagents if reagents is not None else reagent_items(gd) if reagent_slots else None,
                           reagent_slots)[0]
    else:
        rows = [r for r in rows if r["st"].skill_to <= trip.skill + BRING_POINTS] or rows[:1]
    return rows, left, mail


def _bring_items(plan, gd, rows, left, mail, trainer_trips) -> list[tuple[int, int, str]]:
    split = _split(rows, plan, gd, left, mail)
    out = [(i, n, src) for (i, src), n in sorted(split.items())]
    if trainer_trips == ONE_GO:  # nothing to fetch on the way back: your own crafts come along
        out += [(i, n, YOURS) for i, n in _made_earlier(rows, gd).items()]
    return out


def bring_list(plan, gd, trip, bag_slots: int | None, owned: dict | None = None, reagent_slots: int = 0,
              reagents=None, start_skills: dict[int, int] | None = None,
              trainer_trips: str = AS_NEEDED) -> tuple[int, list[tuple[int, int, str]]]:
    """What to bring to a remote rank trainer to keep levelling there: (skill it reaches, items).
    owned: your bank (the stock file); without it, what the planner takes from the bank. Rows before
    the trip use the bank first, as on the shopping list. reagent_slots: a reagent bag holds mats
    first (`reagents`: the set from reagent_items, built here when not given); CRAFT_ROOM stays on
    normal slots. start_skills: profession -> the route's start skill; with it, the stretch also ends at the
    profession's next visit for trainer recipes (trips.visits): the player levels at home and comes back.
    trainer_trips "one_go": the list covers the whole stretch (trips.stretch_end), however many bag slots it takes,
    and your own crafts and disenchants from earlier on the route that it uses (source "yours")."""
    rows, left, mail = _bring_rows(plan, gd, trip, bag_slots, owned, reagent_slots, reagents, start_skills,
                                   trainer_trips)
    if not rows:
        return trip.skill, []
    return rows[-1]["st"].skill_to, _bring_items(plan, gd, rows, left, mail, trainer_trips)


def _carried(gd, items, reagents, reagent_slots) -> tuple[dict, dict, tuple[int, int]]:
    """(item -> count, stack sizes, (normal slots, reagent bag slots)) for carrying bring-list items."""
    total = _sum({i: n} for i, n, _src in items)
    stack = stacks(gd, total)
    return total, stack, carried_split(total, stack, reagents, reagent_slots)


def _lower_goal(plan, gd, rows, left, mail, trainer_trips, bag_slots, reagents, reagent_slots) -> int | None:
    """The highest skill whose bring list (rows up to it) fits in bag_slots, CRAFT_ROOM kept free; None when not even
    the first row's does."""
    for k in range(len(rows) - 1, 0, -1):
        items = _bring_items(plan, gd, rows[:k], dict(left), copy.deepcopy(mail), trainer_trips)
        if _carried(gd, items, reagents, reagent_slots)[2][0] <= bag_slots - CRAFT_ROOM:
            return rows[k - 1]["st"].skill_to
    return None


def bring_text(plan, gd, trip, bag_slots, owned=None, reagent_slots: int = 0,
               services_known: bool = False, start_skills: dict[int, int] | None = None,
               trainer_trips: str = AS_NEEDED) -> str:
    """services_known: the row already says what is near the trainer (or that it is a capital).
    start_skills, trainer_trips: see bring_list. With bag_slots, a list that doesn't fit in them (CRAFT_ROOM kept
    free, the reagent bag taking reagents first) says so, with the highest skill whose list fits."""
    reagents = reagent_items(gd) if reagent_slots else None
    rows, left, mail = _bring_rows(plan, gd, trip, bag_slots, owned, reagent_slots, reagents, start_skills,
                                   trainer_trips)
    if not rows:
        return ""
    start = dict(left), copy.deepcopy(mail)
    items = _bring_items(plan, gd, rows, left, mail, trainer_trips)
    if not items:
        return ""
    reach = rows[-1]["st"].skill_to
    where = {"mail": "from the mail", "bank": "from the bank", "vendor": "from a vendor", YOURS: "yours"}
    parts = [f"{n} {gd.name(i)} ({where[src] if src in where else 'mail from ' + from_character(src)})"
             for i, n, src in items]
    total, stack, split = _carried(gd, items, reagents, reagent_slots)
    note = pack_note(gd, total, stack, "them at the trainer")
    town = "" if services_known else "the town may have no auction house, mailbox or bank, so "
    warn = ""
    if bag_slots and split[0] > bag_slots - CRAFT_ROOM:
        lower = _lower_goal(plan, gd, rows, *start, trainer_trips, bag_slots, reagents, reagent_slots)
        warn = (f" This needs {split[0] + CRAFT_ROOM} free slots and you have {bag_slots}: get bigger bags, bank what "
                f"this stretch doesn't need, or set a lower goal{f' (for example {lower})' if lower else ''} so it fits.")
    return (f" Bring: {', '.join(parts)}: enough to craft to {reach} at the trainer "
            f"({slots_text(split)}{'; ' + note if note else ''}); "
            f"{town}buy and collect before you go.{warn}")


def _patterns(plan, gd, market) -> list[tuple[str, str, float]]:
    out = []
    for _p, _s, spell, how in plan.learn_log:
        r = gd.recipes.get(spell)
        if how in ("ah", "vendor") and r and r.scroll_item:
            cost = (market.min_price(r.scroll_item) or 0) if how == "ah" else gd.vendor_prices.get(r.scroll_item, 0)
            out.append((gd.name(r.scroll_item), "AH" if how == "ah" else "vendor", cost))
    return out


def _bill(plan, gd, market, stock, rows) -> list[tuple[str, int | str, str, float]]:
    """The shopping list's lines, (item, count, where, cost): what to buy for the route's rows, the
    patterns and the trainer's ranks and recipes."""
    owned = {i: float(n) for i, n in stock.items.items()}  # the buffer comes from the bank while it lasts
    split = _split(rows, plan, gd, dict(owned), _mail(plan, whole_pool=True))
    out = []
    for (i, src), n in sorted(split.items(), key=lambda x: (x[0][1], gd.name(x[0][0]))):
        if src == "bank" or from_character(src) is not None:  # nothing to buy
            continue
        cost = ((gd.vendor_prices.get(i) or (gd.items[i].buy_price if i in gd.items else 0)) * n if src == "vendor"
                else market.buy_cost(i, n) or (market.min_price(i) or 0) * n)
        out.append((gd.name(i), n, "vendor" if src == "vendor" else "AH", cost))
    for name, where, cost in _patterns(plan, gd, market):
        out.append((name, 1, where, cost))
    fees = plan.fees + sum(gd.recipes[s].fee for _p, _s, s, how in plan.learn_log if how == "trainer")
    if fees:
        out.append(("Trainer: ranks and recipes", "", "trainer", fees))
    return out


def gold_to_bring(plan, gd, market, stock) -> float:
    """The shopping list's "Gold to bring", in copper: whole crafts with the buffer, patterns and fees."""
    return sum(cost for *_line, cost in _bill(plan, gd, market, stock, route_rows(plan, gd)))


def render_shopping(plan, gd, market, stock) -> tuple[list[str], int | None]:
    """The '## Shopping list' section (and '## Mailbox trips' when the stock gives free bag slots);
    returns the lines and the number of mailbox trips (None without a bag count)."""
    rows = route_rows(plan, gd)
    owned = {i: float(n) for i, n in stock.items.items()}
    lines = ["## Shopping list", "",
             "Counts are for whole crafts, buffer included: you never run short, and nothing is left over "
             "that is too little for another craft.", "",
             "| Item | Count | Where | Cost |", "|---|---:|---|---:|"]
    bill = _bill(plan, gd, market, stock, rows)
    lines += [f"| {name} |{f' {n} ' if n != '' else ' '}| {where} | {gold(cost)} |" for name, n, where, cost in bill]
    lines += ["", f"**Gold to bring: {gold(sum(cost for *_line, cost in bill))}**", ""]
    if not stock.bag_slots:
        return lines, None
    stack = stacks(gd, {i for r in rows for i in r["need"]})
    bag = stock.reagent_slots
    reagents = reagent_items(gd) if bag else None  # once per render
    trips = group_trips(rows, stock.bag_slots - CRAFT_ROOM, stack, reagents, bag)
    lines += ["## Mailbox trips", "",
              f"Planned for {stock.bag_slots} free bag slots"
              + (f" and {bag} reagent bag slots" if bag else "") + "; bought materials wait in the mail.", ""]
    left, mail = dict(owned), _mail(plan, whole_pool=True)
    for t, trip in enumerate(trips, 1):
        parts = {"mail": [], "vendor": [], "bank": [], "other": []}
        for (i, src), n in sorted(_split(trip, plan, gd, left, mail).items(),
                                  key=lambda x: (gd.name(x[0][0]), x[0][1])):
            who = from_character(src)
            if who is None:
                parts[src].append(f"{n} {gd.name(i)}")
            else:
                parts["other"].append(f"{n} {gd.name(i)} (mail from {who})")
        first, last = trip[0]["st"], trip[-1]["st"]
        need: dict[int, float] = {}
        for r in trip:
            for i, q in r["need"].items():
                need[i] = need.get(i, 0) + q
        whole = {i: math.ceil(q - 1e-6) for i, q in need.items()}
        note = pack_note(gd, whole, stack, "them as you craft")
        normal, in_bag = carried_split(whole, stack, reagents, bag)
        stacks_text = f"{normal + in_bag} stacks" + (f" ({normal} bag, {in_bag} reagent bag)" if bag else "")
        lines.append(f"- 📬 **Trip {t}** (skill {first.skill_from}–{last.skill_to}, {stacks_text})."
                     + (f" From the mail: {', '.join(parts['mail'])}." if parts["mail"] else "")
                     + (f" From a vendor: {', '.join(parts['vendor'])}." if parts["vendor"] else "")
                     + (f" From the bank: {', '.join(parts['bank'])}." if parts["bank"] else "")
                     + (f" Mailed by your other characters: {', '.join(parts['other'])}." if parts["other"] else "")
                     + (f" {note[0].upper()}{note[1:]}." if note else ""))
    return [*lines, ""], len(trips)
