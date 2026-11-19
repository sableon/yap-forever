"""A readable levelling guide: what to keep while levelling, the route in skill ranges, money."""
import math
import re
import tomllib

from yap_forever.config import STATIC_DIR
from yap_forever.costmodel import BARS, ORES, STONES
from yap_forever.gamedata import BS, ENCH, PROFESSIONS
from yap_forever.planner import DISENCHANT as DE_SPELL, START_CAP, step_factor
from yap_forever.talents import talent_lines
from yap_forever.trips import trips

with open(STATIC_DIR / "sources.toml", "rb") as _f:
    SOURCES = {group: {int(k): v for k, v in items.items()} for group, items in tomllib.load(_f).items()}
with open(STATIC_DIR / "disenchant.toml", "rb") as _f:
    DE_MATS = {m[0] for band in tomllib.load(_f)["band"]
               for m in (band.get("dust"), band.get("essence"), band.get("shard")) if m}

GROUPS = ["Mining", "Skinning", "Cloth", "Enchanting materials", "Drops and AH"]
EVENT = re.compile(r"^(" + "|".join(PROFESSIONS.values()) + r") (\d+): (.*)$")
BY_NAME = {v: k for k, v in PROFESSIONS.items()}
STAGE_CAPS = (75, 150, 225, 300)  # each stage ends with training the next rank
DISENCHANT = re.compile(r"^disenchant ([\d.]+) (.*)$")
UNNAMED = re.compile(r"\bspell (\d+)\b")


def recipe_name(spell: int, name: str, gd) -> str:
    """Some recipes have no name in the client data; show the item they make instead."""
    r = gd.recipes.get(spell)
    if UNNAMED.fullmatch(name) and r and r.output:
        return gd.name(r.output[0])
    return name


def _fix_names(text: str, gd) -> str:
    return UNNAMED.sub(lambda m: recipe_name(int(m.group(1)), m.group(0), gd), text)


def source_group(item: int, gd) -> str:
    """How you get an item: Mining, Skinning, Cloth, Enchanting materials, Vendor, or Drops and AH."""
    if item in ORES or item in BARS or item in STONES or item in SOURCES["mining"] or _stone_made(item, gd):
        return "Mining"
    if item in SOURCES["skinning"]:
        return "Skinning"
    if item in SOURCES["cloth"]:
        return "Cloth"
    if item in DE_MATS:
        return "Enchanting materials"
    if item in gd.vendor_prices:
        return "Vendor"
    return "Drops and AH"


def _stone_made(item: int, gd):
    """(stone, count) if item is a grinding or sharpening stone made from one kind of stone."""
    for r in gd.recipes.values():
        if r.output and r.output[0] == item and len(r.reagents) == 1:
            (stone, q), = r.reagents.items()
            if stone in STONES:
                return stone, q / r.output[1]
    return None


def count(q: float) -> str:
    return f"{math.ceil(q - 1e-6):,}"


def gold(copper: float) -> str:
    c = int(round(copper))
    if c >= 1000000:  # from 100g, silver is under 1% of the amount
        return f"{c / 10000:,.0f}g"
    if c >= 10000:
        return f"{c / 10000:.1f}g"
    if c >= 100:
        return f"{c // 100}s"
    return f"{c}c"


def _add(into: dict, more: dict) -> None:
    for i, q in more.items():
        into[i] = into.get(i, 0) + q


def _title(caps, route) -> str:
    names = [PROFESSIONS.get(p, str(p)) for p in caps]
    if len(set(caps.values())) == 1:
        title = " + ".join(names) + f" to {next(iter(caps.values()))}"
    else:
        title = " + ".join(f"{n} to {c}" for n, c in zip(names, caps.values()))
    return title + (f" — {route} route" if route else "")


def render_guide(plan, gd, market, stock, caps=None, route="", comparison="", alts=None,
                 character=None, reading="relative") -> str:
    """caps: profession -> target (default Blacksmithing and Enchanting to the stock's target).
    alts: recipe spell -> what skipping its trip costs (None: no other way), from trips.trip_alternatives.
    character, reading: the profile.Character and Working Overtime reading, for the talent lines."""
    caps = caps or {BS: stock.target, ENCH: stock.target}
    out = [f"# {_title(caps, route)}", ""]
    if comparison:
        out += [comparison, ""]
    intro = []
    if len(caps) > 1:
        intro.append("Level both professions side by side: craft in whichever one is lower.")
    if stock.mining or plan.farm:
        intro.append("Until you switch, gather and keep the materials below instead of selling them.")
    if intro:
        out += [" ".join(intro), ""]
    for line in talent_lines(character, reading, plan, caps, stock):
        out += [line, ""]
    _keep(out, plan, gd, market)
    _route(out, plan, gd, caps, stock, alts or {})
    from yap_forever.shopping import render_shopping  # shopping imports this module
    out += render_shopping(plan, gd, market, stock)[0]
    _money(out, plan, stock)
    _notes(out, plan, market, gatherer=bool(stock.mining or plan.farm))
    return "\n".join(out) + "\n"


# --- keep while levelling ------------------------------------------------------
def _whole(plan, gd) -> dict[int, dict]:
    """id(step) -> its shopping row: counts in whole crafts, as the shopping list buys them."""
    from yap_forever.shopping import route_rows  # shopping imports this module
    return {id(st): r for r in route_rows(plan, gd) for st in r["parts"]}


def _less(counts: dict, minus: dict) -> dict:
    out = {i: q - minus.get(i, 0) for i, q in counts.items()}
    return {i: q for i, q in out.items() if q > 1e-9}


def _keep(out, plan, gd, market) -> None:
    need, bank = {}, {}
    rows, seen = _whole(plan, gd), set()
    for s in plan.steps:
        row = rows.get(id(s))
        if row is None:
            _add(need, {i: q * step_factor(s) for i, q in s.materials.items()})
        elif id(row) not in seen:
            seen.add(id(row))
            _add(need, _less(row["need"], row["tools"]))  # a bought tool is no material to keep
        _add(bank, s.from_stock)
    groups: dict[str, list] = {}
    for item, q in need.items():
        groups.setdefault(source_group(item, gd), []).append(item)

    out += ["## Keep while levelling", "",
            "Counts are for the whole route and include a 15% buffer on yellow and green steps, "
            "where skill-ups are a matter of luck. *Buy later* is what the part you still need would cost "
            "on your AH today, so the top rows are the ones most worth keeping.", ""]
    for group in GROUPS:
        items = groups.get(group)
        if not items:
            continue
        rows = []
        for item in items:
            still = max(0.0, need[item] - bank.get(item, 0))
            rows.append((_buy_later(item, still, market), item, still))
        rows.sort(key=lambda r: -r[0][0])
        out += [f"### {group}", "", "| Item | Keep | In bank | Still to get | Buy later |",
                "|---|---|---|---|---|"]
        for (_, price), item, still in rows:
            out.append(f"| {_label(item, gd)} | {count(need[item])} | {count(bank.get(item, 0))} "
                       f"| {count(still)} | {price} |")
        out.append("")
        out += _group_notes(group, items, gd)

    vendor = groups.get("Vendor", [])
    if vendor:
        total = sum(need[i] * gd.vendor_prices.get(i, 0) for i in vendor)
        listed = ", ".join(f"{count(need[i])} {gd.name(i)}" for i in sorted(vendor, key=lambda i: -need[i]))
        out += ["### Buy from a vendor when you switch", "",
                f"No need to stockpile: {listed}. About {gold(total)} in total.", ""]


def _buy_later(item, still, market) -> tuple[float, str]:
    if still < 1e-6:
        return 0, "—"
    cost = market.buy_cost(item, math.ceil(still - 1e-6))
    if cost is not None:
        return cost, gold(cost)
    low = market.min_price(item)
    if low is None:
        return 0, "not on AH"
    return low * still, f"{gold(low * still)} (only {market.depth(item)} listed)"


def _label(item, gd) -> str:
    made = _stone_made(item, gd)
    if made:
        stone, q = made
        return f"{gd.name(item)} (or {q:g} {gd.name(stone)} each)"
    return gd.name(item)


def _group_notes(group, items, gd) -> list[str]:
    notes = []
    if group == "Mining":
        bars = [i for i in items if i in BARS]
        if bars:
            notes.append("Bars: mine the ore and smelt it. Bronze = Copper + Tin; "
                         "Steel = Iron + Coal (Coal from a vendor).")
        unused = [n for i, n in SOURCES["mining"].items() if i not in items]
    elif group == "Skinning":
        unused = [n for i, n in SOURCES["skinning"].items() if i not in items]
    elif group == "Enchanting materials":
        notes.append("Disenchanting your own greens already covers part of Enchanting; "
                     "these are the extra materials on top.")
        unused = []
    else:
        unused = []
    if unused:
        notes.append("Safe to sell, the route doesn't use them: " + ", ".join(unused) + ".")
    return notes + ([""] if notes else [])


# --- route ---------------------------------------------------------------------
def _trip_line(t, alts, plan=None, gd=None, bag_slots=None, owned=None) -> str:
    if t.kind == "rank":
        from yap_forever.shopping import bring_text  # shopping imports this module
        return (f"- **Trip:** {t.what}: the trainer is in a set town (the planner doesn't say where yet). "
                "While there, learn the trainer recipes your skill allows."
                + (bring_text(plan, gd, t, bag_slots, owned) if plan is not None else ""))
    if t.kind == "vendor":
        line = (f"- **Trip:** buy the pattern for {t.what} from a vendor (patterns are sold in particular "
                "towns); buy every vendor pattern the route uses on one visit: patterns can be bought before "
                "you can learn them")
    else:
        line = f"- **Trip:** the Merchant's Favor vendor (one place per faction) for {t.what}"
    if t.spell in alts:
        diff = alts[t.spell]
        line += ("; there is no other way to reach the target without it" if diff is None
                 else "; or skip it at no extra cost" if diff <= 0.5
                 else f"; or skip it: +{gold(diff)} for the route without it")
    return line + "."


def _route(out, plan, gd, caps, stock, alts) -> None:
    quest_limit = stock.quest_item_sales
    used_by: dict[int, list[str]] = {}
    for s in plan.steps:
        for item in s.used_made:
            name = recipe_name(s.spell_id, s.name, gd)
            if name not in used_by.setdefault(item, []):
                used_by[item].append(name)
    disenchanted = {m.group(3) for e in plan.events if (m := EVENT.match(e))}
    disenchanted = {t.split(" ", 2)[2] for t in disenchanted if t.startswith("disenchant ")}
    held = {gd.name(i) for i in plan.held_for_de}

    trained = {p: sorted(s for q, s, _c, _f in plan.ranks if q == p) for p in caps}
    first = {}
    for p in caps:
        start = max(1, stock.skills.get(p, 1))
        cap0 = min([c for c in [START_CAP] + [r.cap for r in gd.trainer_ranks.get(p, [])] if c >= start],
                   default=START_CAP)
        first[p] = (start, STAGE_CAPS.index(cap0) if cap0 in STAGE_CAPS else 0)

    def stage(p, skill, event):
        """Rows from a training skill on belong to the next stage; events at it close the current one."""
        return first[p][1] + sum(1 for t in trained[p] if (t < skill if event else t <= skill))

    whole = _whole(plan, gd)
    lines: dict[tuple[int, int], list] = {}  # (stage, profession) -> [(skill, order, text)]
    for p in caps:
        steps = [s for s in plan.steps if s.profession == p and s.skill_from < s.skill_to]
        groups: dict[int, list] = {}
        for s in steps:
            groups.setdefault(stage(p, s.skill_from, False), []).append(s)
        for k, group in groups.items():
            for r in _ranges(group, gd, whole):
                lines.setdefault((k, p), []).append(
                    (r["from"], 1, _range_line(r, gd, used_by, disenchanted | held, quest_limit, plan.kept_greens)))
        for s in plan.steps:
            if s.profession == p and s.skill_from == s.skill_to:  # the goal recipe, crafted once
                row = whole.get(id(s))
                bring, made = (row["need"], row["earlier"]) if row else (s.materials, s.used_made)
                mats = ", ".join([f"{count(q)} {gd.name(i)}" for i, q in bring.items()]
                                 + [f"{count(q)} {gd.name(i)} (made earlier)" for i, q in made.items()])
                text = f"- **Craft {recipe_name(s.spell_id, s.name, gd)} once**" + (f" — {mats}" if mats else "")
                lines.setdefault((stage(p, s.skill_from, True), p), []).append((s.skill_from, 3, text))
    de: dict[str, list] = {}  # item name -> [first skill, last skill, count]
    for e in plan.events:
        m = EVENT.match(e)
        if not m or BY_NAME[m.group(1)] not in caps:
            continue
        p, at, text = BY_NAME[m.group(1)], int(m.group(2)), m.group(3)
        if text.startswith("craft ") and text.endswith(" once"):
            continue  # shown as its row
        d = DISENCHANT.match(text)
        if d:
            first_at, _last, n = de.get(d.group(2), [at, at, 0])
            de[d.group(2)] = [first_at, at, n + float(d.group(1))]
            continue
        lines.setdefault((stage(p, at, True), p), []).append((at, 0, f"- *At {at}: {_fix_names(text, gd)}*"))
    for item, (first_at, last, n) in de.items():
        text = (f"- *At {first_at}: disenchant {count(n)} {item}*" if first_at == last else
                f"- *From {first_at}: disenchant your {item} as you make them ({count(n)} in all, by {last})*")
        lines.setdefault((stage(ENCH, first_at, True), ENCH), []).append((first_at, 2, text))
    for t in trips(plan, gd):
        if t.profession in caps:
            lines.setdefault((stage(t.profession, t.skill, True), t.profession), []).append(
                (t.skill, 0.5, _trip_line(t, alts, plan, gd, stock.bag_slots, stock.items)))

    out += ["## Route", ""]
    for k in sorted({k for k, _p in lines}):
        out += [f"### Stage {k + 1}: to {STAGE_CAPS[min(k, len(STAGE_CAPS) - 1)]}", ""]
        for p in caps:
            part = sorted(lines.get((k, p), []), key=lambda x: (x[0], x[1]))
            if not part:
                continue
            n = k - first[p][1]
            lo = trained[p][n - 1] if n > 0 else first[p][0]
            hi = trained[p][n] if n < len(trained[p]) else plan.final_skill.get(p, lo)
            out += [f"**{PROFESSIONS.get(p, p)} {lo}–{hi}**", ""] + [t for _, _, t in part] + [""]


def _ranges(steps, gd, rows=None) -> list[dict]:
    """rows: id(step) -> shopping row; a step with a row shows its whole crafts and their counts."""
    out: list[dict] = []
    seen = set()
    for s in steps:
        row = (rows or {}).get(id(s))
        here = {}
        if row and id(row) in seen:  # a later part of a run already counted with its first part
            crafts, mats, own = 0, {}, {}
        elif row:
            seen.add(id(row))
            crafts, mats, own = row["n"] + row["more"], _less(row["need"], row["tools"]), dict(row["earlier"])
            here = dict(row["here"])  # bought tools are left out: the route shows each purchase
        else:
            k = step_factor(s)
            crafts = s.crafts * k
            mats = {i: q * k for i, q in s.materials.items()}
            own = {i: q * k for i, q in s.used_made.items()}
        last = out[-1] if out else None
        if last and last["spell"] == s.spell_id and last["to"] == s.skill_from:
            last["to"] = s.skill_to
            last["crafts"] += crafts
            _add(last["mats"], mats)
            _add(last["own"], own)
            _add(last["here"], here)
        else:
            out.append({"spell": s.spell_id, "name": recipe_name(s.spell_id, s.name, gd), "from": s.skill_from,
                        "to": s.skill_to, "crafts": crafts, "mats": mats, "own": own, "here": here})
    return out


def _range_line(r, gd, used_by, for_de, quest_limit=None, kept=frozenset()) -> str:
    # Disenchants are an expected count of greens you already have, not a buffered shopping count.
    n = max(1, round(r["crafts"]) if r["spell"] == DE_SPELL else math.ceil(r["crafts"] - 1e-6))
    mats = [f"{count(q)} {gd.name(i)}" for i, q in r["mats"].items()] + \
           [f"{count(q)} {gd.name(i)} (yours)" for i, q in r["own"].items()]
    line = f"- **{r['from']}–{r['to']}** · {n}× {r['name']}"
    if mats:
        line += " — " + ", ".join(mats)
    if r.get("here"):  # intermediates still missing, crafted on the spot from the materials listed
        line += "; first craft " + ", ".join(f"{count(q)} {gd.name(i)}" for i, q in r["here"].items())
    recipe = gd.recipes.get(r["spell"])
    if recipe and recipe.output:
        item = recipe.output[0]
        if item in used_by:
            line += f" → keep for {', '.join(used_by[item])}"
        elif gd.name(item) in for_de:
            line += " → keep for disenchanting"
        elif item in kept:
            line += " → keep for disenchanting on another character"
        elif item in gd.quest_items and quest_limit is not None:
            line += f" → sell up to {quest_limit} on the AH (quest item), the rest to a vendor"
        elif item in gd.quest_items:
            line += " → sell on the AH (quest item, steady demand)"
        else:
            line += " → sell (up to 5 on the AH, the rest to a vendor)"
    return line


# --- money and notes -------------------------------------------------------------
def _money(out, plan, stock) -> None:
    out += ["## Money", "",
            f"- **Spent along the way:** about {gold(plan.cash_total)}, including {gold(plan.fees)} of "
            "trainer ranks. It is spread over the whole route, and sales come in as you go.",
            f"- **Back from selling crafts:** about {gold(plan.sale_proceeds)}.",
            f"- **Net:** about {gold(abs(plan.economic_total))} "
            f"{'cost' if plan.economic_total > 0 else 'profit'}, counting your bank and mined bars "
            "at what they would sell for.",
            f"- **Merchant's Favor:** {plan.favor_spent} of {stock.favor} spent.", ""]


def _notes(out, plan, market, gatherer=True) -> None:
    out += ["## Notes", ""]
    for reason in plan.stall_reasons.values():
        out.append(f"- Stops early: {reason}.")
    if any("quest from" in e for e in plan.events):
        out.append("- Imperial Plate plans come from quests that need character level 50; "
                   "bring the Thorium Bars shown in the route.")
    if gatherer:
        out += ["- Leather is costed as bought on the AH; since you skin, gather it instead.",
                "- Stones are counted as mined along with the ore."]
    out += [f"- Prices: your AH snapshot of {market.snapshot_time or 'unknown time'}.", ""]
