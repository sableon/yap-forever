"""Markdown report for a plan."""
import math
from collections import defaultdict

from yap_forever.costmodel import Valuer, money
from yap_forever.gamedata import BS, ENCH, PROFESSIONS, QUESTIE_SHA, SKILLUP_SHA, WAGO_BUILD
from yap_forever.planner import DISENCHANT, step_factor
from yap_forever.prices import source_line
from yap_forever.shared import SHARED_NOTE, Budget, mail_text
from yap_forever.talents import talent_lines

SECTIONS = ["Verdict", "Farm before switching", "Switch order", "Route", "Merchant's Favor",
            "Totals", "Sell now", "Excluded recipes", "Data notes"]


def _main_pair(caps) -> bool:
    """The Blacksmithing + Enchanting switch with Mining that the farm and switch sections describe."""
    return caps is None or set(caps) == {BS, ENCH}


def verdict(plan, stock, caps=None) -> str:
    ore = sum(plan.farm.values())
    if not _main_pair(caps) and ore == 0:
        return "Ready to level"
    if ore == 0:
        return "Switch now"
    if ore <= stock.short_farm_ore:
        return "Switch after a short farm"
    return "Not yet"


def _budget_text(cash: float, stock, budget: Budget | None) -> str:
    """Whether the route's cash fits the gold: the group's shared gold, or this character's own `cash_gold`
    when the caller names no group."""
    if budget is None:
        over = cash - stock.cash
        return (f"over your {money(stock.cash)} budget by {money(over)}" if over > 0
                else f"within your {money(stock.cash)} budget")
    over = cash - budget.copper
    shared = f"{money(budget.copper)} shared by your {budget.label} characters"
    return f"over the {shared} by {money(over)}" if over > 0 else f"within the {shared}"


def _q(item, gd):
    return " (quest item)" if item in gd.quest_items else ""


def render(plan, verdict_text, market, gd, stock, favor, caps=None, character=None,
           reading="relative", today=None, saving_line="", budget: Budget | None = None) -> str:
    v = Valuer(market, gd, stock)
    names = " + ".join(PROFESSIONS.get(x, str(x)) for x in (caps or (BS, ENCH)))
    out: list[str] = [f"# {names} plan", ""]
    prices_line = source_line(market, today)
    if prices_line:
        out += [prices_line, ""]

    def section(name):
        out.extend(["", f"## {name}", ""])

    # Verdict
    section("Verdict")
    out.append(f"**{verdict_text}.**")
    if plan.farm:
        out.append(f"Mining still needed for {sum(plan.farm.values())} ore "
                   f"(a short farm is up to {stock.short_farm_ore}, set in stock.toml).")
    for prof, reason in plan.stall_reasons.items():
        out.append(f"- Stops early: {reason}.")
    final = ", ".join(f"{PROFESSIONS[p]} {s}" for p, s in plan.final_skill.items())
    out.append(f"Planned to: {final}.")

    # Farm
    if _main_pair(caps) or plan.farm:
        section("Farm before switching")
    if plan.farm:
        out += ["| Ore | Count |", "|---|---|"]
        out += [f"| {gd.name(i)} | {n} |" for i, n in sorted(plan.farm.items())]
        bars = ", ".join(f"{math.ceil(n)} {gd.name(b)}" for b, n in sorted(plan.farmed_bars.items()))
        out += ["", f"Smelts into: {bars}."]
    elif _main_pair(caps):
        out.append("Nothing: your stock and purchases cover the route.")

    # Switch order
    held_total = sum(n for n in plan.de_materials.values())
    if not _main_pair(caps):
        if held_total:
            out.append(f"Disenchanting in this route yields about {held_total:.0f} materials.")
    else:
        _switch_order(out, section, held_total)

    pair = caps or {BS: stock.target, ENCH: stock.target}
    _rest(out, section, plan, v, market, gd, stock, favor, talent_lines(character, reading, plan, pair, stock),
          saving_line, budget)
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"


def _switch_order(out, section, held_total) -> None:
    section("Switch order")
    out.append("Farming time is free, so both orders cost the same gold.")
    out.append("- **Order A:** drop Skinning and take Blacksmithing now, keep Mining while levelling "
               "Blacksmithing (mine the list above as you go), then swap Mining for Enchanting. "
               "Greens already in your bank that Enchanting can disenchant are disenchanted first; "
               "a green craft is only kept for disenchanting once Enchanting can disenchant it.")
    out.append("- **Order B:** farm the list first, then switch both. Both professions level side by side, "
               "so greens are disenchanted as soon as Enchanting allows.")
    if held_total:
        out.append(f"Disenchanting in this route yields about {held_total:.0f} materials.")


def _rest(out, section, plan, v, market, gd, stock, favor, talents=(), saving_line="", budget=None) -> None:
    # Route
    section("Route")
    out += ["| Profession | Skill | Craft | Crafts | Cash | Net cost |", "|---|---|---|---|---|---|"]
    for s in plan.steps:
        n = max(1, round(s.crafts)) if s.spell_id == DISENCHANT else math.ceil(s.crafts * step_factor(s) - 1e-6)
        out.append(f"| {PROFESSIONS[s.profession]} | {s.skill_from}→{s.skill_to} | {s.name} | "
                   f"{n} | {money(s.cash)} | {money(s.economic)} |")
    if plan.events:
        out += ["", "**Milestones**", ""] + [f"- {e}" for e in plan.events]
    if plan.crafted:
        out += ["", "**Crafted for reagents** (made on the way, already counted above): "
                + ", ".join(f"{math.ceil(n - 1e-9)} {gd.name(i)}" for i, n in sorted(plan.crafted.items())) + "."]
    if plan.bought or plan.vendor_bought:
        out += ["", "**Shopping list**", "", "| Item | Count | Where | Cost | Note |", "|---|---|---|---|---|"]
        for i, n in sorted(plan.bought.items(), key=lambda kv: gd.name(kv[0])):
            c = market.buy_cost(i, math.ceil(n - 1e-9))
            thin = "thin market" if n >= 0.5 * market.depth(i) else ""
            out.append(f"| {gd.name(i)} | {math.ceil(n - 1e-9)} | AH | {money(c or 0)} | {thin} |")
        for i, n in sorted(plan.vendor_bought.items(), key=lambda kv: gd.name(kv[0])):
            out.append(f"| {gd.name(i)} | {math.ceil(n - 1e-9)} | vendor | "
                       f"{money(gd.vendor_prices.get(i, 0) * n)} | |")
    if plan.used_stock:
        used = ", ".join(f"{math.ceil(n - 1e-9)} {gd.name(i)}" for i, n in sorted(plan.used_stock.items()))
        out += ["", f"From your stock: {used}."]
    if plan.used_mail:
        out += ["", f"From your other characters, by mail: {mail_text(plan.used_mail, gd.name)}."]

    # Favor
    section("Merchant's Favor")
    fav_events = [e for e in plan.events if "Favor)" in e]
    out.append(f"Spent {plan.favor_spent} of {stock.favor} Favor.")
    out += [f"- {e}" for e in fav_events]
    if favor.turnins:
        out += ["", "Crate turn-ins, cheapest Favor first (materials at what they'd sell for; "
                "the crate at its AH price):", "",
                "| Turn-in | Favor | Value given up | Per Favor |", "|---|---|---|---|"]
        rows = []
        for t in favor.turnins:
            total, unknown = 0.0, []
            for i, n in t.items.items():
                price = v.owned_value(i) * n
                if price == 0:
                    ah = market.buy_cost(i, n)
                    if ah is None:
                        unknown.append(gd.name(i))
                        continue
                    price = ah
                total += price
            note = f" + {', '.join(unknown)} (no price)" if unknown else ""
            rows.append((total / t.favor, t, total, note))
        for per, t, total, note in sorted(rows, key=lambda r: r[0]):
            out.append(f"| {t.name} | {t.favor} | {money(total)}{note} | {money(per)} |")

    # Totals
    section("Totals")
    out.append(f"- **Cash needed:** {money(plan.cash_total)} ({_budget_text(plan.cash_total, stock, budget)}), "
               "before any sales.")
    out.append(f"- Trainer fees included: {money(plan.fees)}.")
    out.append(f"- **Expected sales of crafted leftovers:** {money(plan.sale_proceeds)}.")
    out.append(f"- Leftover disenchant materials worth {money(plan.leftover_value)}.")
    out.append(f"- **Full economic cost:** {money(plan.economic_total)} "
               "(cash + your stock and farmed bars at what they'd sell for − sales − leftovers).")

    # Sell now
    section("Sell now")
    spare = []
    for i, n in stock.items.items():
        left = n - plan.used_stock.get(i, 0)
        ns = market.net_sell(i)
        if left >= 1 and ns:
            spare.append((ns * left, i, left))
    no_market = [i for i, n in stock.items.items() if n and market.depth(i) == 0]
    if no_market:
        out += ["Stock with no market (no AH listings; valued at vendor price): "
                + ", ".join(gd.name(i) for i in sorted(no_market)) + ".", ""]
    if spare:
        out += ["Stock the route doesn't use:", ""]
        out += [f"- {math.floor(n)} {gd.name(i)}: about {money(val)}" for val, i, n in sorted(spare, reverse=True)]
    if plan.leftovers:
        out += ["", "Crafted along the way (sell, or keep for quests):", ""]
        out += [f"- {math.floor(n)} {gd.name(i)}{_q(i, gd)}"
                for i, n in sorted(plan.leftovers.items(), key=lambda kv: -kv[1]) if n >= 1]
    profit = []
    for spell in plan.learned:
        r = gd.recipes.get(spell)
        if not r or not r.output:
            continue
        sell = market.net_sell(r.output[0])
        cost = 0
        for i, q in r.reagents.items():
            opt = v.buy_option(i, q, 0)
            if opt is None:
                cost = None
                break
            cost += opt[1]
        if sell and cost is not None and sell * r.output[1] > cost:
            profit.append((sell * r.output[1] - cost, r))
    if profit:
        out += ["", "Crafts that sell above material cost (one at a time):", ""]
        out += [f"- {r.name}{_q(r.output[0], gd)}: +{money(gain)} each"
                for gain, r in sorted(profit, key=lambda x: -x[0])[:15]]
    tips = []
    for spell in plan.learned:
        r = gd.recipes.get(spell)
        if r and r.skill_line == ENCH and not r.output:
            cost = sum((v.buy_option(i, q, 0) or (None, 0))[1] for i, q in r.reagents.items())
            tips.append((cost, r))
    if tips:
        out += ["", "Enchants you'll know, for tips (material cost per cast):", ""]
        out += [f"- {r.name}: {money(c)}" for c, r in sorted(tips, key=lambda x: x[0])]

    # Excluded
    section("Excluded recipes")
    by_reason = defaultdict(list)
    for spell, reason in plan.skipped:
        r = gd.recipes.get(spell)
        if r and r.required_skill <= 225:
            key = reason.split(":")[0]
            by_reason[key].append(r.name + (f" ({reason.split(': ', 1)[1]})" if ": " in reason else ""))
    if not by_reason:
        out.append("None.")
    for reason, names in sorted(by_reason.items()):
        out.append(f"- **{reason}** ({len(names)}): {', '.join(sorted(names))}")

    # Notes
    section("Data notes")
    if market.source == "auctionator":  # the limits of an import are stated at the top of the report
        out.append(f"- Prices: Auctionator scan of {market.scan_day or 'unknown date'}.")
    else:
        out.append(f"- AH snapshot: {market.snapshot_time or 'unknown'}.")
    out.append(f"- Recipes: skillup-forever {SKILLUP_SHA[:7]}; client tables wago.tools {WAGO_BUILD}; "
               f"quest items: QuestieDB {QUESTIE_SHA[:7]}.")
    out.append("- Disenchant results use Classic odds (estimates). Favor data is from community guides.")
    out.append("- AH resale of crafted gear counts at most 5 of each item, except quest items.")
    out.append("- Leather is not farmed in this model; any leather is bought.")
    if budget is not None and budget.is_sum:
        out.append(f"- The {budget.label} gold is the sum of `cash_gold` in your characters' stock files; "
                   f"set it once under [gold] in profile.toml (\"{budget.label}\" = gold).")
    if plan.used_mail:
        out.append(f"- {SHARED_NOTE}")
    out += [f"- {line}" for line in talents]
    if saving_line:
        out.append(f"- {saving_line}")
