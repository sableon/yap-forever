"""A readable levelling guide: what to keep while levelling, the route in skill ranges, money."""
import math
import re
import tomllib
from dataclasses import dataclass

from yap_forever.config import STATIC_DIR
from yap_forever.costmodel import BARS, ORES, STONES, money
from yap_forever.gamedata import ENCH, PROFESSIONS
from yap_forever.planner import DISENCHANT as DE_SPELL, START_CAP, reached_lines, step_factor
from yap_forever import trainer_text
from yap_forever.prices import source_line
from yap_forever.shared import SHARED_NOTE, mail_text
from yap_forever.talents import lowest_profession, talent_lines
from yap_forever.trainers import RANK_BY_CAP
from yap_forever.trips import before_start, recipe_rank_cap, trips, visits

with open(STATIC_DIR / "sources.toml", "rb") as _f:
    SOURCES = {group: {int(k): v for k, v in items.items()} for group, items in tomllib.load(_f).items()}
with open(STATIC_DIR / "disenchant.toml", "rb") as _f:
    DE_MATS = {m[0] for band in tomllib.load(_f)["band"]
               for m in (band.get("dust"), band.get("essence"), band.get("shard")) if m}

COPPER_PER_GOLD = 10000
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
    c = round(copper)
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


def _gathers(plan, stock) -> bool:
    """The character mines, or the plan farms ore (it can with Mining 0 and a mining_goal: costmodel.farmable)."""
    return bool(stock.mining or stock.mining_goal or plan.farm)


NOTHING_IN_BUDGET = "Nothing to craft within this budget."


def _title(caps, route) -> str:
    names = [PROFESSIONS.get(p, str(p)) for p in caps]
    if len(set(caps.values())) == 1:
        title = " + ".join(names) + f" to {next(iter(caps.values()))}"
    else:
        title = " + ".join(f"{n} to {c}" for n, c in zip(names, caps.values(), strict=True))
    return title + (f" — {route} route" if route else "")


def render_guide(plan, gd, market, stock, caps, route="", comparison="", alts=None,
                 character=None, reading="relative", today=None, trainer_info=None, trainer_note="",
                 saving_line="", mode="gold", study_hint_gold_per_point=100, extra_notes=(),
                 budget_lines=(), order=None, nothing_in_budget=False, trainer_trips="as_needed") -> str:
    """caps: profession -> target skill (see planner.resolve_goals).
    alts: Trip.key (a recipe, or a recipe trip's recipes) -> what skipping the trip costs (None: no other way),
    from trips.trip_alternatives.
    character, reading: the profile.Character and Working Overtime reading, for the talent lines.
    today: the date the staleness of imported prices is judged against (default: today).
    trainer_info: trainer_text.TrainerInfo, to name trainers on rank rows (None: say a set town);
    trainer_note: why trainers are left out, said once at the top.
    saving_line: what a route planned at the Forever listing could cost less ("": none).
    mode: "gold" or "value", the measure the route was planned for (a row's cost per point is in it).
    study_hint_gold_per_point: a row of the lowest profession at this many gold a point gets a Dedicated Study hint.
    extra_notes: lines for the Notes section (a character's stock file that was left out of the plan).
    budget_lines: what a budget goal reaches (budget.lines), said under the comparison.
    order: the professions raised one at a time, in this order (None: side by side).
    nothing_in_budget: the budget reaches no stop (budget.BudgetCut.below_first_stop): the route says so.
    trainer_trips: the character's "as_needed" or "one_go" (profile.Character.trainer_trips; see trips.visits)."""
    out = [f"# {_title(caps, route)}", ""]
    prices_line = source_line(market, today)
    if prices_line:
        out += [prices_line, ""]
    if comparison:
        out += [comparison, ""]
    if budget_lines:
        out += [" ".join(budget_lines), ""]
    intro = []
    if len(caps) > 1 and order:
        first, second = (PROFESSIONS.get(p, str(p)) for p in order[:2])
        intro.append(f"Level one profession at a time: {first} first, then {second}.")
    elif len(caps) > 1:
        intro.append("Level both professions side by side: craft in whichever one is lower.")
    if _gathers(plan, stock):
        intro.append("Gather and keep the materials below instead of selling them.")
    if intro:
        out += [" ".join(intro), ""]
    if trainer_note:
        out += [trainer_note, ""]
    for line in talent_lines(character, reading, plan, caps, stock) + ([saving_line] if saving_line else []):
        out += [line, ""]
    from yap_forever.shopping import mailed  # shopping imports this module
    by_mail = mailed(plan, gd, stock) if plan.used_mail else {}  # the shopping list's counts
    _keep(out, plan, gd, market, by_mail, stock)
    hint = _StudyHint(lowest_profession(caps, stock), mode, study_hint_gold_per_point, character)
    _route(out, plan, gd, caps, stock, alts or {}, trainer_info, hint, trainer_trips, market)
    if nothing_in_budget:
        out += [NOTHING_IN_BUDGET, ""]
    from yap_forever.shopping import render_shopping  # shopping imports this module
    out += render_shopping(plan, gd, market, stock)[0]
    _money(out, plan, stock)
    _notes(out, plan, market, gatherer=_gathers(plan, stock), skins=bool(stock.skinning),
           mailed=by_mail, gd=gd, notes=extra_notes)
    return "\n".join(out) + "\n"


# --- keep while levelling ------------------------------------------------------
def _whole(plan, gd) -> dict[int, dict]:
    """id(step) -> its shopping row: counts in whole crafts, as the shopping list buys them."""
    from yap_forever.shopping import route_rows  # shopping imports this module
    return {id(st): r for r in route_rows(plan, gd) for st in r["parts"]}


def _less(counts: dict, minus: dict) -> dict:
    out = {i: q - minus.get(i, 0) for i, q in counts.items()}
    return {i: q for i, q in out.items() if q > 1e-9}


def _keep(out, plan, gd, market, by_mail=None, stock=None) -> None:
    """by_mail: item -> (character, count) mailed by your other characters, as the shopping list counts it.
    stock: the character's, for the notes that only fit a miner."""
    need, bank = {}, {}
    mail = {i: sum(n for _who, n in sources) for i, sources in (by_mail or {}).items()}
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
    for item in need:
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
            still = max(0.0, need[item] - bank.get(item, 0) - mail.get(item, 0))
            rows.append((_buy_later(item, still, market), item, still))
        rows.sort(key=lambda r: -r[0][0])
        by_mail = any(mail.get(item) for item in items)  # a column only when another character mails some
        out += [f"### {group}", "",
                "| Item | Keep | In bank |" + (" By mail |" if by_mail else "") + " Still to get | Buy later |",
                "|---|---|---|" + ("---|" if by_mail else "") + "---|---|"]
        for (_, price), item, still in rows:
            out.append(f"| {_label(item, gd)} | {count(need[item])} | {count(bank.get(item, 0))} "
                       + (f"| {count(mail.get(item, 0))} " if by_mail else "")
                       + f"| {count(still)} | {price} |")
        out.append("")
        out += _group_notes(group, items, gd, bool(stock and _gathers(plan, stock)))

    vendor = groups.get("Vendor", [])
    if vendor:
        total = sum(need[i] * gd.vendor_prices.get(i, 0) for i in vendor)
        listed = ", ".join(f"{count(need[i])} {gd.name(i)}" for i in sorted(vendor, key=lambda i: -need[i]))
        out += ["### Buy from a vendor", "",
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


def _group_notes(group, items, gd, mines=True) -> list[str]:
    notes = []
    if group == "Mining":
        bars = [i for i in items if i in BARS]
        if bars and mines:
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
def _skip(key, alts) -> str:
    """'; or skip it: +X for the route without it' for a trip in alts (trips.trip_alternatives), else ""."""
    if key not in alts:
        return ""
    diff = alts[key]
    return ("; there is no other way to reach the target without it" if diff is None
            else "; or skip it at no extra cost" if diff <= 0.5
            else f"; or skip it: +{gold(diff)} for the route without it")


def _names(spells, gd, fees) -> str:
    """'A (10s 0c), B (4s 50c)' (fees: with each recipe's trainer fee, when it has one, to the copper as on the route's
    "Learn" rows)."""
    rs = [(s, gd.recipes[s]) for s in spells]
    return ", ".join(recipe_name(s, r.name, gd) + (f" ({money(r.fee)})" if fees and r.fee else "") for s, r in rs)


def _visit_text(v, gd, learn=True) -> str:
    """What a trainer visit's row says to learn: the recipes the route needs later ("While there, learn: ...")
    and those reachable from the start ("If you don't have them yet: ..."). "" for nothing."""
    out = []
    if learn and v.learn:
        out.append(f"While there, learn: {_names(v.learn, gd, True)}.")
    if v.if_missing:
        it = "it" if len(v.if_missing) == 1 else "them"
        out.append(f"If you don't have {it} yet: {_names(v.if_missing, gd, False)}.")
    return " ".join(out)


def _before_start(profession, spells, gd) -> list[str]:
    """'- **Before you start**, make sure you know: A, B (any Artisan Blacksmith teaches them).', one row per
    rank that teaches them."""
    by_rank: dict[int, list[int]] = {}
    for spell in spells:
        by_rank.setdefault(recipe_rank_cap(gd.recipes[spell].required_skill), []).append(spell)
    return [f"- **Before you start**, make sure you know: "
            f"{', '.join(recipe_name(s, gd.recipes[s].name, gd) for s in group)} "
            f"(any {RANK_BY_CAP[cap]} {trainer_text.person(profession)} teaches {'it' if len(group) == 1 else 'them'})."
            for cap, group in sorted(by_rank.items())]


def _city_stop(v, gd, trainer_info, planned, said, named) -> str | None:
    """The row (with its dash) of a trainer visit below the remote ranks: a rank trained in a capital, or a
    stop there only for recipes; None for a rank row the guide can't name trainers for and nothing to learn.
    said, named: what earlier rows of the guide already said (see trainer_text.city_row)."""
    rank, person = RANK_BY_CAP[v.rank_cap], trainer_text.person(v.profession)
    if v.kind == "rank":
        row = trainer_text.city_row(trainer_info, v.profession, v.rank_cap, planned, said, named=named)
        if row is None and (v.learn or v.if_missing):
            row = f"Train {PROFESSIONS.get(v.profession, v.profession)} to {v.rank_cap} at any {rank} {person} in a capital."
        more = _visit_text(v, gd)
    else:  # "city": a stop only to learn recipes
        lead = f"Learn {_names(v.learn, gd, True)}"
        row = (trainer_text.city_row(trainer_info, v.profession, v.rank_cap, planned, said, lead, named, True)
               or f"{lead} at any {rank} {person} in a capital.")
        more = _visit_text(v, gd, learn=False)
    if row is None:
        return None
    return f"- {row}" + (f" {more}" if more else "")


def _reached_text(v, gd) -> str:
    """'Learn at the trainer as you reach them: A at 240, B at 251.' for a "one_go" rank visit (Visit.as_reached),
    in skill order; "" for none."""
    if not v.as_reached:
        return ""
    parts = [f"{recipe_name(spell, gd.recipes[spell].name, gd)} at {skill}"
             for spell, skill in sorted(v.as_reached, key=lambda x: x[1])]
    return f"Learn at the trainer as you reach them: {', '.join(parts)}."


def _trip_line(t, alts, plan=None, gd=None, bag_slots=None, owned=None, reagent_slots=0,
               trainer_info=None, level=None, start_skills=None, trainer_trips="as_needed", market=None) -> str:
    """start_skills: profession -> the route's start skill, so a rank trip's bring list ends at the next trip
    back for recipes (shopping.bring_list). trainer_trips: "one_go" lists the recipes to learn there as the skill
    reaches them, and brings everything to the end of the stretch. market: today's prices (shopping.bring_text)."""
    known = t.visit is not None and gd is not None
    learn = " ".join(x for x in (_visit_text(t.visit, gd), _reached_text(t.visit, gd))
                     if x) if known else ""
    if t.kind == "rank":
        from yap_forever.shopping import bring_text  # shopping imports this module
        stop = trainer_text.remote_stop(trainer_info, t.profession, t.cap, level)
        where = "the trainer is in a set town (the planner doesn't say where yet)." if stop is None else stop.text
        return (f"- **Trip:** {t.what}: {where}" + (f" {learn}" if learn else "")
                + (bring_text(plan, gd, t, bag_slots, owned, reagent_slots, bool(stop and stop.services_known),
                              start_skills, trainer_trips, market) if plan is not None else ""))
    if t.kind == "recipe":
        names = _names(t.visit.learn, gd, True) if known else t.what
        missing = _visit_text(t.visit, gd, learn=False) if known else ""
        return (f"- **Trip:** back to {trainer_text.trip_trainer(trainer_info, t.profession, t.cap)}, at {t.skill} "
                f"for {names}{_skip(t.key, alts)}." + (f" {missing}" if missing else ""))
    if t.kind == "vendor":
        line = (f"- **Trip:** buy the pattern for {t.what} from a vendor (patterns are sold in particular "
                "towns); buy every vendor pattern the route uses on one visit: patterns can be bought before "
                "you can learn them")
    elif t.kind == "favor":
        line = f"- **Trip:** the Merchant's Favor vendor (one place per faction) for {t.what}"
    else:
        raise ValueError(f"unknown trip kind {t.kind!r}")
    return line + _skip(t.key, alts) + "."


@dataclass(frozen=True)
class _StudyHint:
    """Where a route row is priced high enough, per point, to point at Dedicated Study."""
    profession: int
    mode: str  # "gold" or "value": the measure the route was planned for
    gold_per_point: float
    character: object  # profile.Character or None

    def note(self, prof: int, r: dict) -> str:
        points = r["to"] - r["from"]
        cost = r["cash"] if self.mode == "gold" else r["economic"]
        if prof != self.profession or points < 1 or cost / points < self.gold_per_point * COPPER_PER_GOLD - 1e-9:
            return ""
        days = f"{points} day" + ("" if points == 1 else "s")
        cover = "this point" if points == 1 else f"these {points} points"
        text = f" — about {gold(cost / points)} a point here: Dedicated Study (one free point a day) would cover {cover} in {days}"
        if not (self.character and self.character.dedicated_study):
            text += " (a legacy talent you haven't taken)"
        return text


def _route(out, plan, gd, caps, stock, alts, trainer_info=None, hint=None, trainer_trips="as_needed",
           market=None) -> None:
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
                line = _range_line(r, gd, used_by, disenchanted | held, quest_limit, plan.kept_greens)
                lines.setdefault((k, p), []).append((r["from"], 1, line + (hint.note(p, r) if hint else "")))
        for s in plan.steps:
            if s.profession == p and s.skill_from == s.skill_to:  # the goal recipe, crafted once
                row = whole.get(id(s))
                bring, made = (row["need"], row["earlier"]) if row else (s.materials, s.used_made)
                mats = ", ".join([f"{count(q)} {gd.name(i)}" for i, q in bring.items()]
                                 + [f"{count(q)} {gd.name(i)} (made earlier)" for i, q in made.items()])
                text = f"- **Craft {recipe_name(s.spell_id, s.name, gd)} once**" + (f" — {mats}" if mats else "")
                lines.setdefault((stage(p, s.skill_from, True), p), []).append((s.skill_from, 3, text))
    listed = _listed_notes(plan, gd)
    learned = _learned_at(plan, gd, trainer_info, stock.skills, trainer_trips)
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
        name = text.split(" (", 1)[0].removeprefix("Learn ")
        note, where = listed.get((p, at, name), ""), learned.get((p, at, name)) if text.startswith("Learn ") else None
        if where:  # learned at a visit (its row has the fee) or before the start: shown after the visit's row
            text = f"start crafting {name} ({where})"
        lines.setdefault((stage(p, at, True), p), []).append(
            (at, 0.75 if where else 0, f"- *At {at}: {trainer_text.add_note(_fix_names(text, gd), note)}*"))
    for item, (first_at, last, n) in de.items():
        text = (f"- *At {first_at}: disenchant {count(n)} {item}*" if first_at == last else
                f"- *From {first_at}: disenchant your {item} as you make them ({count(n)} in all, by {last})*")
        lines.setdefault((stage(ENCH, first_at, True), ENCH), []).append((first_at, 2, text))
    for t in trips(plan, gd, stock.skills, trainer_trips):
        if t.profession in caps:
            lines.setdefault((stage(t.profession, t.skill, True), t.profession), []).append(
                (t.skill, 0.5, _trip_line(t, alts, plan, gd, stock.bag_slots, stock.items, stock.reagent_slots,
                                          trainer_info, stock.level, stock.skills, trainer_trips, market)))
    planned, said, named = tuple(caps), set(), set()
    # in the order the guide shows them, so a city's "different parts" sentence is on its first row
    for v in sorted((v for v in visits(plan, gd, stock.skills, trainer_trips) if not v.remote and v.profession in caps),
                    key=lambda v: (stage(v.profession, v.skill, True), planned.index(v.profession), v.skill)):
        row = _city_stop(v, gd, trainer_info, planned, said, named)
        if row:
            lines.setdefault((stage(v.profession, v.skill, True), v.profession), []).append((v.skill, 0.5, row))
    for p, spells in before_start(plan, gd, stock.skills).items():
        if p in caps:
            lines.setdefault((stage(p, first[p][0], True), p), []).extend(
                (first[p][0], -1, text) for text in _before_start(p, spells, gd))

    out += ["## Route", ""]
    for line in reached_lines(plan):
        out += [line, ""]
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


def _listed_notes(plan, gd) -> dict[tuple[int, int, str], str]:
    """(profession, skill, recipe name) -> the note for a trainer recipe the route learns above the skill
    the Forever data lists it from (gamedata.safe_requirements raised it)."""
    out = {}
    for prof, at, spell, how in plan.learn_log:
        r = gd.recipes.get(spell)
        if how == "trainer" and r and r.listed_skill is not None and r.listed_skill < at:
            out[(prof, at, r.name)] = trainer_text.listed_note(r.listed_skill)
    return out


def _learned_at(plan, gd, trainer_info, start_skills, trainer_trips="as_needed") -> dict[tuple[int, int, str], str]:
    """(profession, skill, recipe name) -> where a trainer recipe the route learns there was learned instead:
    "learned at <trainer>" (a visit that learns it ahead, or lists it as "if you don't have it yet") or
    "learned before you start" (trips.before_start). Recipes a "one_go" visit learns as the skill reaches them
    (Visit.as_reached) keep their own "Learn" row, with the fee."""
    where: dict[int, str] = {}
    for v in visits(plan, gd, start_skills, trainer_trips):
        label = trainer_text.visit_trainer(trainer_info, v.profession, v.rank_cap, v.remote)
        where.update({s: f"learned at {label}" for s in v.learn + v.if_missing})
    for spells in before_start(plan, gd, start_skills).values():
        where.update({s: "learned before you start" for s in spells})
    return {(prof, at, gd.recipes[spell].name): where[spell] for prof, at, spell, how in plan.learn_log
            if how == "trainer" and spell in where}


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
            last["cash"] += s.cash
            last["economic"] += s.economic
            _add(last["mats"], mats)
            _add(last["own"], own)
            _add(last["here"], here)
        else:
            out.append({"spell": s.spell_id, "name": recipe_name(s.spell_id, s.name, gd), "from": s.skill_from,
                        "to": s.skill_to, "crafts": crafts, "mats": mats, "own": own, "here": here,
                        "cash": s.cash, "economic": s.economic})
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


def _notes(out, plan, market, gatherer=True, mailed=None, gd=None, notes=(), skins=False) -> None:
    """mailed: item -> (character, count) your other characters are asked to mail (shopping.mailed).
    notes: further lines the caller wants said (a character's file that was left out)."""
    out += ["## Notes", ""]
    out += [f"- {line}" for line in notes]
    if mailed and gd is not None:
        out += [f"- From your other characters, by mail: {mail_text(mailed, gd.name)}.", f"- {SHARED_NOTE}"]
    for reason in plan.stall_reasons.values():
        out.append(f"- Stops early: {reason}.")
    if any("quest from" in e for e in plan.events):
        out.append("- Imperial Plate plans come from quests that need character level 50; "
                   "bring the Thorium Bars shown in the route.")
    if gatherer:
        out += ["- Leather is costed as bought on the AH" + ("; since you skin, gather it instead." if skins else "."),
                "- Stones are counted as mined along with the ore."]
    if market.source == "auctionator":  # the limits of an import are stated at the top of the guide
        out.append(f"- Prices: Auctionator scan of {market.scan_day or 'unknown date'}.")
    else:
        out.append(f"- Prices: your AH snapshot of {market.snapshot_time or 'unknown time'}.")
    out.append("")
