import dataclasses
import datetime
import unittest

from tests import toy
from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import gold, render_guide, source_group
from yap_forever.trainer_text import TrainerInfo
from tests.test_planner import BARS, base_recipes, run

BS, ENCH = 164, 333
ALCH, ENG, TAILOR = 171, 202, 197
GROUPS = (frozenset({TAILOR, ALCH, ENCH}), frozenset({BS, ENG}), frozenset({165}))


def guide(recipes, listings, stock=None, cap=60):
    st = stock or toy.stock()
    p = run(recipes, listings, stock=st, cap=cap)
    gd = toy.gamedata(recipes)
    return render_guide(p, gd, toy.market(listings), st, {BS: 225, ENCH: 225})


def auctionator_market(scan_day="2026-11-18", dropped=0):
    m = toy.market({toy.COPPER_BAR: [(100, 50)]})
    m.source, m.scan_day, m.dropped = "auctionator", scan_day, dropped
    return m


LINE = ("Prices: Auctionator scan of 2026-11-18 (one price and one count per item, no listing depth: costs are "
        "a lower bound, and the supplier note and buyout flag use that one count).")


class PricesHeaderTests(unittest.TestCase):
    def render(self, market, today):
        recipes = base_recipes()
        st = toy.stock()
        p = run(recipes, {toy.COPPER_BAR: [(100, 50)]}, stock=st, cap=60)
        return render_guide(p, toy.gamedata(recipes), market, st, {BS: 225, ENCH: 225}, today=today)

    def test_fresh_auctionator_scan_header_is_the_exact_line_under_the_title(self):
        text = self.render(auctionator_market(), datetime.date(2026, 11, 20))
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# "))
        self.assertEqual(lines[2], LINE)
        self.assertNotIn("days old", text)
        self.assertIn("- Prices: Auctionator scan of 2026-11-18.", text)
        self.assertNotIn("AH snapshot", text)

    def test_the_three_days_the_docs_promise(self):
        from yap_forever import auctionator, prices
        self.assertEqual((prices.STALE_DAYS, auctionator.FRESH_DAYS), (3, 3))

    def test_three_days_old_is_still_fresh_four_is_stale(self):
        self.assertNotIn("days old", self.render(auctionator_market(), datetime.date(2026, 11, 21)))
        text = self.render(auctionator_market(), datetime.date(2026, 11, 22))
        self.assertIn(LINE + " This scan is 4 days old: scan again for current prices.", text)

    def test_dropped_items_are_counted_in_the_same_line(self):
        text = self.render(auctionator_market(dropped=3), datetime.date(2026, 11, 19))
        self.assertIn(LINE + " 3 items left out: not listed or older than 3 days.", text)
        text = self.render(auctionator_market(dropped=3), datetime.date(2026, 11, 30))
        self.assertIn(LINE + " This scan is 12 days old: scan again for current prices. "
                      "3 items left out: not listed or older than 3 days.", text)

    def test_api_prices_keep_todays_header(self):
        recipes = base_recipes()
        st = toy.stock()
        p = run(recipes, {toy.COPPER_BAR: [(100, 50)]}, stock=st, cap=60)
        m = toy.market({toy.COPPER_BAR: [(100, 50)]})
        m.snapshot_time = "T"
        text = render_guide(p, toy.gamedata(recipes), m, st, {BS: 225, ENCH: 225}, today=datetime.date(2030, 1, 1))
        self.assertNotIn("Auctionator", text)
        self.assertNotIn("days old", text)
        self.assertEqual(text.splitlines()[1], "")
        self.assertIn("- Prices: your AH snapshot of T.", text)

    def test_unknown_scan_day_does_not_crash(self):
        text = self.render(auctionator_market(scan_day=""), datetime.date(2026, 11, 20))
        self.assertIn("Auctionator scan of unknown date", text)
        self.assertIn("Scan date unknown: scan again for current prices.", text)
        text = self.render(auctionator_market(scan_day="garbage"), datetime.date(2026, 11, 20))
        self.assertNotIn("days old", text)
        self.assertIn("Scan date unknown: scan again for current prices.", text)


class GoldTests(unittest.TestCase):
    def test_silver_shown_below_100g(self):
        from yap_forever.guide import gold
        self.assertEqual(gold(105000), "10.5g")  # 10g 50s
        self.assertEqual(gold(995000), "99.5g")
        self.assertEqual(gold(15000), "1.5g")

    def test_whole_gold_from_100g(self):
        from yap_forever.guide import gold
        self.assertEqual(gold(1000000), "100g")
        self.assertEqual(gold(12345678), "1,235g")

    def test_small_amounts(self):
        from yap_forever.guide import gold
        self.assertEqual(gold(250), "2s")
        self.assertEqual(gold(42), "42c")

    def test_negative_amounts(self):
        # #97: a route whose crafts sell back to vendors for more than it spends has a total value below zero
        from yap_forever.guide import gold
        self.assertEqual(gold(-4321), "-43s")
        self.assertEqual(gold(-54321), "-5.4g")
        self.assertEqual(gold(-1234567), "-123g")
        self.assertEqual(gold(-42), "-42c")


class SourceGroupTests(unittest.TestCase):
    def test_groups(self):
        gd = toy.gamedata([])
        self.assertEqual(source_group(2836, gd), "Mining")       # Coarse Stone
        self.assertEqual(source_group(toy.COPPER_BAR, gd), "Mining")
        self.assertEqual(source_group(1210, gd), "Mining")       # Shadowgem
        self.assertEqual(source_group(4304, gd), "Skinning")     # Thick Leather
        self.assertEqual(source_group(2589, gd), "Cloth")        # Linen Cloth
        self.assertEqual(source_group(toy.DUST, gd), "Enchanting materials")
        self.assertEqual(source_group(toy.ROD, gd), "Vendor")    # vendor-sold in toy data
        self.assertEqual(source_group(toy.ODD, gd), "Drops and AH")


class GuideTests(unittest.TestCase):
    def test_sections(self):
        text = guide(base_recipes(), BARS)
        for heading in ("## Keep while levelling", "## Route", "## Money"):
            self.assertIn(heading, text)

    def test_keep_list_shows_bank_and_still_to_get(self):
        text = guide(base_recipes(), BARS, stock=toy.stock({toy.COPPER_BAR: 20}))
        row = next(l for l in text.splitlines() if l.startswith("| Copper Bar"))
        self.assertEqual([c.strip() for c in row.split("|")[2:5]], ["59", "20", "39"])

    def test_route_merges_skill_range(self):
        text = guide(base_recipes(), BARS)
        self.assertIn("**1–60** · 59× BS basic", text)

    def test_yellow_steps_carry_15_percent_buffer_rounded_up(self):
        # Thresholds (1, 1, 6, 11): yellow from 1, green from 6, grey at 11. Expected crafts 29.29.
        rs = [toy.recipe(1, "BS yellow", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), t=(1, 1, 6, 11)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        text = guide(rs, BARS, cap=11)
        self.assertIn("**1–11** · 34× BS yellow", text)  # ceil(29.29 * 1.15)
        row = next(l for l in text.splitlines() if l.startswith("| Copper Bar"))
        self.assertEqual(row.split("|")[2].strip(), "34")

    def test_orange_steps_have_no_buffer(self):
        text = guide(base_recipes(), BARS)
        self.assertIn("**1–60** · 59× BS basic", text)

    def test_orange_run_in_one_profession_has_no_buffer(self):
        # Enchanting already at 60: Blacksmithing runs 1-60 alone, which the planner merges into one step.
        text = guide(base_recipes(), BARS, stock=toy.stock(skills={ENCH: 60}))
        self.assertIn("**1–60** · 59× BS basic", text)
        row = next(l for l in text.splitlines() if l.startswith("| Copper Bar"))
        self.assertEqual(row.split("|")[2].strip(), "59")

    def test_bank_greens_disenchanted_first(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        text = guide(rs, {**BARS, toy.DUST: [(300, 100000)]}, stock=toy.stock({toy.BELT: 30}), cap=40)
        self.assertIn("*At 1: disenchant 30 Runed Copper Belt from your bank*", text)
        line = next(l for l in text.splitlines() if "Disenchant greens" in l)
        self.assertTrue(line.startswith("- **1–"), line)
        self.assertIn("30 Runed Copper Belt", line)
        row = next(l for l in text.splitlines() if l.startswith("| Runed Copper Belt"))
        self.assertEqual([c.strip() for c in row.split("|")[2:5]], ["30", "30", "0"])

    def test_disenchants_not_more_than_greens(self):
        import re
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        text = guide(rs, {**BARS, toy.DUST: [(300, 100000)]}, cap=40)
        des = sum(int(n) for n in re.findall(r"· (\d+)× Disenchant greens", text))
        belts = int(re.search(r"· (\d+)× Belt", text).group(1))
        self.assertGreater(des, 0)
        self.assertLessEqual(des, belts)

    def test_reused_craft_noted(self):
        rs = [toy.recipe(1, "Copper Rod", BS, {toy.COPPER_BAR: 1}, (toy.ROD, 1)),
              toy.recipe(2, "Ench rod", ENCH, {toy.ROD: 1})]
        text = guide(rs, {**BARS, toy.ROD: [(100000, 1000)]}, cap=40)
        self.assertIn("keep for Ench rod", text)
        self.assertIn("Copper Rod (yours)", text)

    def test_vendor_items_not_in_keep_tables(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        text = guide(rs, BARS)
        keep = text[text.index("## Keep while levelling"):text.index("## Route")]
        self.assertFalse(any(l.startswith("| Copper Rod") for l in keep.splitlines()))
        self.assertIn("### Buy from a vendor\n", text)

    def test_bought_tool_not_a_material_on_rows_or_keep_table(self):
        from yap_forever.guide import render_guide
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = run(rs, BARS)
        gd = toy.gamedata(rs)
        guide = render_guide(p, gd, toy.market(BARS), toy.stock(), caps={BS: 225, ENCH: 225})
        keep = guide[guide.index("## Keep while levelling"):guide.index("## Route")]
        self.assertNotIn("Blacksmith Hammer", keep)
        rows = [l for l in guide.splitlines() if l.startswith("- **") and "× BS hammer" in l]
        self.assertTrue(rows)
        self.assertFalse(any("Blacksmith Hammer" in l for l in rows))

    def test_reached_target_is_said(self):
        from tests.test_planner import run_caps
        rs = base_recipes()
        st = toy.stock(skills={BS: 300})
        p = run_caps(rs, {BS: 300}, BARS, stock=st)
        text = render_guide(p, toy.gamedata(rs), toy.market(BARS), st, {BS: 300})
        route = text[text.index("## Route"):text.index("## Money")]
        self.assertIn("Blacksmithing is already at 300: nothing to plan.", route)

    def test_vendor_heading_has_no_switch(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        text = guide(rs, BARS)
        self.assertIn("### Buy from a vendor\n", text)
        self.assertNotIn("when you switch", text)

    def test_bars_note_only_for_miners(self):
        for mining, expected in ((120, True), (0, False)):
            with self.subTest(mining=mining):
                text = guide(base_recipes(), BARS, stock=toy.stock(mining=mining))
                self.assertIn("### Mining", text)
                self.assertEqual("Bars: mine the ore" in text, expected)

    def test_bars_note_when_the_plan_farms_with_a_mining_goal(self):
        st = toy.stock(mining=0)
        st.mining_goal = 150  # farms ore without mining yet (costmodel.farmable)
        text = guide(base_recipes(), BARS, stock=st)
        self.assertIn("Bars: mine the ore", text)

    def test_gathering_intro_has_no_switch(self):
        text = guide(base_recipes(), BARS, stock=toy.stock(mining=120))
        self.assertIn("Gather and keep the materials below instead of selling them.", text)
        self.assertNotIn("Until you switch", text)

    def test_skin_clause_only_for_skinners(self):
        for skinning, expected in ((100, True), (0, False)):
            with self.subTest(skinning=skinning):
                st = toy.stock(mining=120)  # the leather note sits with the gatherer notes
                st.skinning = skinning
                text = guide(base_recipes(), BARS, stock=st)
                self.assertIn("Leather is costed as bought on the AH", text)
                self.assertEqual("since you skin" in text, expected)


if __name__ == "__main__":
    unittest.main()


class ReadabilityTests(unittest.TestCase):
    def test_disenchant_events_collapse_to_one_line(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        text = guide(rs, {**BARS, toy.DUST: [(300, 100000)]}, cap=40)
        lines = [l for l in text.splitlines() if "disenchant" in l and "Runed Copper Belt" in l]
        self.assertEqual(len(lines), 1, lines)

    def test_unnamed_recipe_shows_item_name(self):
        rs = [toy.recipe(9, "spell 9", BS, {toy.COPPER_BAR: 1}, (toy.VEST, 1)),  # unnamed: "spell <id>"
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        text = guide(rs, BARS)
        self.assertNotIn("spell 9", text)
        self.assertIn("× Copper Chain Vest", text)


class QuestItemNoteTests(unittest.TestCase):
    def test_quest_item_note_shows_limit(self):
        import dataclasses
        rs = [toy.recipe(1, "Vest", BS, {toy.COPPER_BAR: 1}, (toy.VEST, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        st = dataclasses.replace(toy.stock(), quest_item_sales=20)
        gd = toy.gamedata(rs, quest_items=[toy.VEST])
        listings = {**BARS, toy.VEST: [(5000, 3)]}
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        p = plan(gd, Valuer(toy.market(listings), gd, st), st, toy.NO_FAVOR, caps={BS: 60, ENCH: 60})
        text = render_guide(p, gd, toy.market(listings), st, {BS: 225, ENCH: 225})
        self.assertIn("sell up to 20 on the AH (quest item, about 47s each), the rest to a vendor", text)


LW = 165


def lw_plan(spans, ranks, extra_events=()):
    """A Leatherworking plan from (from, to) spans of one recipe and (skill, cap) trainings."""
    from yap_forever.planner import Plan, Step
    steps = [Step(LW, a, b, 10, "LW basic", b - a, 0, 0, {toy.COPPER_BAR: b - a}) for a, b in spans]
    events = [f"Leatherworking {s}: train rank up to {cap} (4s 50c)" for s, cap in ranks] + list(extra_events)
    return Plan(steps=steps, ranks=[(LW, s, cap, 450) for s, cap in ranks], events=events,
                final_skill={LW: spans[-1][1]})


def lw_gd():
    return toy.gamedata(base_recipes() + [toy.recipe(10, "LW basic", LW, {toy.COPPER_BAR: 1})])


class AnyProfessionGuideTests(unittest.TestCase):
    def test_guide_title_for_one_profession(self):
        p = lw_plan([(1, 40)], [])
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={LW: 40})
        self.assertEqual(text.splitlines()[0], "# Leatherworking to 40")
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={LW: 40}, route="least gold")
        self.assertEqual(text.splitlines()[0], "# Leatherworking to 40 — least gold route")

    def test_guide_title_two_targets(self):
        p = lw_plan([(1, 40)], [])
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={197: 225, ENCH: 150})
        self.assertEqual(text.splitlines()[0], "# Tailoring to 225 + Enchanting to 150")

    def test_guide_stage_ends_at_training_skill(self):
        p = lw_plan([(1, 62), (62, 140), (140, 160)], [(62, 150), (140, 225)])
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={LW: 160})
        for line in ("### Stage 1: to 75", "### Stage 2: to 150", "### Stage 3: to 225",
                     "**Leatherworking 1–62**", "**Leatherworking 62–140**", "**Leatherworking 140–160**"):
            self.assertIn(line, text)
        self.assertNotIn("Skill 1–150", text)
        stage1 = text[text.index("### Stage 1"):text.index("### Stage 2")]
        self.assertIn("At 62: train rank up to 150", stage1)

    def test_guide_stage_ends_at_cap_without_window_trip(self):
        p = lw_plan([(1, 75), (75, 90)], [(75, 150)])
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={LW: 90})
        self.assertIn("**Leatherworking 1–75**", text)
        self.assertIn("**Leatherworking 75–90**", text)

    def test_guide_craft_once_row(self):
        from yap_forever.planner import Plan, Step
        rs = base_recipes() + [toy.recipe(5, "BS final", BS, {toy.IRON_BAR: 1}, req=20)]
        p = Plan(steps=[Step(BS, 1, 20, 1, "BS basic", 19, 0, 0), Step(BS, 20, 20, 5, "BS final", 1, 700, 700,
                                                                       {toy.IRON_BAR: 1})],
                 final_skill={BS: 20})
        text = render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(), caps={BS: 20})
        self.assertIn("Craft BS final once", text)
        self.assertNotIn("20–20", text)

    def test_craft_once_row_lists_reagents_made_earlier(self):
        from yap_forever.planner import Plan, Step
        rs = base_recipes() + [toy.recipe(5, "BS final", BS, {toy.IRON_BAR: 1, toy.COPPER_BAR: 2}, req=20)]
        p = Plan(steps=[Step(BS, 1, 20, 1, "BS basic", 19, 0, 0),
                        Step(BS, 20, 20, 5, "BS final", 1, 700, 700, {toy.IRON_BAR: 1},
                             used_made={toy.COPPER_BAR: 2})],
                 final_skill={BS: 20})
        text = render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(), caps={BS: 20})
        line = next(l for l in text.splitlines() if "Craft BS final once" in l)
        self.assertIn("1 Iron Bar", line)
        self.assertIn("2 Copper Bar (made earlier)", line)

    def test_guide_shows_comparison(self):
        p = lw_plan([(1, 40)], [])
        text = render_guide(p, lw_gd(), toy.market(BARS), toy.stock(), caps={LW: 40}, comparison="| x | y |")
        self.assertLess(text.index("| x | y |"), text.index("## Route"))

    def test_guide_trip_notes(self):
        from yap_forever.planner import Plan, Step
        rs = base_recipes() + [toy.recipe(30, "BS scroll", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL)]
        gd = toy.gamedata(rs)
        gd.vendor_prices[toy.SCROLL] = 500
        p = Plan(steps=[Step(BS, 190, 230, 1, "BS basic", 40, 0, 0, {toy.COPPER_BAR: 40})],
                 ranks=[(BS, 200, 300, 9000)], learn_log=[(BS, 195, 30, "vendor")],
                 events=["Blacksmithing 200: train rank up to 300 (90s 0c)"], final_skill={BS: 230})
        st = toy.stock(skills={BS: 190})
        text = render_guide(p, gd, toy.market(BARS), st, caps={BS: 230}, alts={30: 3000})
        rank = next(l for l in text.splitlines() if l.startswith("- **Trip:**") and "rank to 300" in l)
        self.assertIn("set town", rank)
        vendor = next(l for l in text.splitlines() if l.startswith("- **Trip:**") and "BS scroll" in l)
        self.assertIn("buy every vendor pattern the route uses on one visit", vendor)
        self.assertIn("or skip it: +30s", vendor)


class TrainerRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        from yap_forever import trainer_text, trainers
        cls.data = trainers.load_trainer_data(Path(__file__).parent / "fixtures" / "gamedata")
        cls.info = lambda self, faction: trainer_text.TrainerInfo(faction, self.data)

    def route(self, ranks, faction="alliance", events=(), learn_log=(), recipes=None, steps=None, notes=None,
              level=60, **kw):
        from yap_forever.planner import Plan, Step
        rs = (recipes or base_recipes()) + [toy.recipe(11, "BS two", BS, {toy.COPPER_BAR: 1}),
                                            toy.recipe(12, "BS three", BS, {toy.COPPER_BAR: 1}),
                                            toy.recipe(22, "Ench two", ENCH, {toy.ROD: 1})]
        steps = steps or [Step(BS, 1, 200, 1, "BS basic", 199, 0, 0, {toy.COPPER_BAR: 199}),
                          Step(BS, 200, 275, 11, "BS two", 75, 0, 0, {toy.COPPER_BAR: 75}),
                          Step(BS, 275, 300, 12, "BS three", 25, 0, 0, {toy.COPPER_BAR: 25})]
        p = Plan(steps=steps, bought={toy.COPPER_BAR: 299},
                 ranks=[(BS, s, cap, 450) for s, cap in ranks], learn_log=list(learn_log),
                 events=[f"Blacksmithing {s}: train rank up to {cap} (4s 50c)" for s, cap in ranks] + list(events),
                 final_skill={BS: 300})
        info = self.info(faction) if faction else None
        if info and notes is not None:
            info = dataclasses.replace(info, notes=notes)
        return render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(skills={BS: 1}, level=level),
                            caps={BS: 300}, trainer_info=info, **kw)

    def lines(self, text, start):
        return [l for l in text.splitlines() if l.startswith(start)]

    def test_master_row_has_place_and_services(self):
        text = self.route([(60, 150), (200, 225), (275, 300)])
        (row,) = [l for l in self.lines(text, "- **Trip:**") if "rank to 300" in l]
        self.assertTrue(row.startswith("- **Trip:** Blacksmithing rank to 300: Brakka Ironfold, Stranglethorn Vale "
                                       "(30.0, 70.0). Nearby: bank, neutral AH (its own prices and a higher deposit), "
                                       "mailbox. "), row)
        self.assertNotIn("While there", row)  # nothing to learn at this visit
        self.assertNotIn("set town", row)

    def test_booty_bay_style_master_row_says_neutral_auction_house(self):
        text = self.route([(60, 150), (200, 225), (275, 300)])
        (row,) = [l for l in self.lines(text, "- **Trip:**") if "rank to 300" in l]
        self.assertIn("neutral AH (its own prices and a higher deposit)", row)

    def test_master_row_with_notes_from_play(self):
        from yap_forever.trainer_notes import Notes, TrainerNote
        notes = Notes({90001: TrainerNote(reach_level=35, flight_path=True, note="A tip.")}, {})
        ranks = [(60, 150), (200, 225), (275, 300)]
        (row,) = [l for l in self.lines(self.route(ranks, notes=notes, level=40), "- **Trip:**") if "rank to 300" in l]
        self.assertIn("mailbox. Easy to reach from about level 35, with a flight path for repeat visits. A tip.", row)
        (row,) = [l for l in self.lines(self.route(ranks, notes=notes, level=30), "- **Trip:**") if "rank to 300" in l]
        self.assertIn("for repeat visits (you're level 30: the first trip is harder). A tip. Bring:", row)

    def test_trainer_without_notes_row_is_unchanged(self):
        from yap_forever.trainer_notes import Notes, TrainerNote
        ranks = [(60, 150), (200, 225), (275, 300)]
        plain = self.route(ranks)
        self.assertEqual(self.route(ranks, notes=Notes({12345: TrainerNote(reach_level=50)}, {})), plain)
        self.assertEqual(self.route(ranks, notes=Notes({}, {})), plain)

    def test_instance_row_group_and_solo(self):
        from yap_forever.planner import Plan, Step
        from yap_forever.trainer_notes import Notes, TrainerNote
        notes = Notes({90006: TrainerNote(group_level=37, solo_level=52, note="Groups go earlier.")}, {})
        p = Plan(steps=[Step(333, 1, 300, 2, "Ench basic", 299, 0, 0, {toy.ROD: 299})], ranks=[(333, 250, 300, 450)],
                 events=["Enchanting 250: train rank up to 300 (4s 50c)"], final_skill={333: 300})
        for level, tail in ((50, "solo from about level 52. Groups go earlier."),
                            (30, "solo from about level 52 (you're level 30). Groups go earlier.")):
            info = dataclasses.replace(self.info("horde"), notes=notes)
            text = render_guide(p, toy.gamedata(base_recipes()), toy.market(BARS),
                                toy.stock(skills={333: 1}, level=level), caps={333: 300}, trainer_info=info)
            (row,) = self.lines(text, "- **Trip:**")
            self.assertIn("Zarn Runeweaver, inside Uldaman. Go with a group from about level 37, " + tail, row)

    def test_city_row_says_the_cities_tip(self):
        from yap_forever.trainer_notes import Notes
        text = self.route([(60, 150)], faction="alliance", notes=Notes({}, {1519: "A tip."}),
                          recipes=base_recipes())
        # no Expert Blacksmith for the Alliance in a capital in the fixture: no tip, no capital
        (row,) = self.lines(text, "- Train ")
        self.assertNotIn("A tip.", row)
        text = self.route([(60, 150)], faction="horde", notes=Notes({}, {1637: "A tip."}))
        (row,) = self.lines(text, "- Train ")
        self.assertEqual(row, "- Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                              "(for example Grom Anvilhand, Orgrimmar). A tip.")

    SAID = "In Stormwind City, the Alchemy and Engineering trainers are in different parts of the city."

    def city_route(self, planned, ranks, groups=None, tips=None, zone=1519, profs=None):
        """A guide for `planned` professions with a city row for each (profession, from, cap) in `ranks`;
        every profession has an Expert trainer in `zone` (profs: the ones that do)."""
        from yap_forever import trainers
        from yap_forever.planner import Plan
        from yap_forever.trainer_notes import Notes
        from yap_forever.trainer_text import TrainerInfo
        ts = [trainers.Trainer(i, f"Trainer {i}", p, "Expert", "A", zone, (1, 1), True)
              for i, p in enumerate(profs or planned, 1)]
        data = trainers.TrainerData(ts, {}, [], {1519: "Stormwind City", 1537: "Ironforge", 1657: "Darnassus"})
        notes = Notes({}, tips or {}, {1519: GROUPS} if groups is None else groups)
        p = Plan(steps=[], ranks=[(prof, s, cap, 450) for prof, s, cap in ranks],
                 events=[f"{PROFESSIONS[prof]} {s}: train rank up to {cap} (4s 50c)" for prof, s, cap in ranks],
                 final_skill={prof: 150 for prof in planned})
        return render_guide(p, toy.gamedata(base_recipes()), toy.market(BARS), toy.stock(),
                            caps={prof: 150 for prof in planned}, trainer_info=TrainerInfo("alliance", data, notes))

    def test_two_professions_in_different_city_groups_say_so_once(self):
        text = self.city_route([ALCH, ENG], [(ALCH, 60, 150), (ENG, 60, 150)])
        rows = self.lines(text, "- Train ")
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(self.SAID in r for r in rows), 1, rows)
        self.assertTrue(rows[0].endswith(" " + self.SAID), rows[0])  # the city's first row

    def test_the_sentence_is_on_the_first_row_in_the_guide(self):
        text = self.city_route([ENG, ALCH], [(ALCH, 60, 150), (ENG, 60, 150)])
        rows = self.lines(text, "- Train ")
        self.assertIn("Engineering and Alchemy trainers", "".join(rows))
        self.assertTrue(rows[0].startswith("- Train Engineering"), rows)  # profession order in the guide
        self.assertIn("different parts", rows[0])
        self.assertNotIn("different parts", rows[1])

    def test_the_same_city_group_says_nothing(self):
        text = self.city_route([TAILOR, ALCH], [(TAILOR, 60, 150), (ALCH, 60, 150)])
        self.assertNotIn("different parts", text)

    def test_one_planned_profession_says_nothing(self):
        text = self.city_route([ALCH], [(ALCH, 60, 150)], profs=[ALCH, ENG])
        self.assertNotIn("different parts", text)

    def test_a_profession_missing_from_the_groups_says_nothing(self):
        text = self.city_route([ALCH, ENG], [(ALCH, 60, 150), (ENG, 60, 150)],
                               groups={1519: (frozenset({ALCH}), frozenset({BS}))})
        self.assertNotIn("different parts", text)

    def test_darnassus_tip_still_shows(self):
        tip = "Most trainers are close together, but the bank and the AH are far apart."
        text = self.city_route([ALCH, ENG], [(ALCH, 60, 150), (ENG, 60, 150)], zone=1657, tips={1657: tip},
                               groups={})
        rows = self.lines(text, "- Train ")
        self.assertTrue(all(r.endswith(" " + tip) for r in rows), rows)  # the tip is per row, as before

    def test_artisan_row_names_both_alliance_trainers(self):
        text = self.route([(60, 150), (200, 225)])
        (row,) = [l for l in self.lines(text, "- **Trip:**") if "rank to 225" in l]
        self.assertIn("Thessa Hammerlow, Stormwind City (60.5, 40.2). Or Wandering Smith, Ironforge (20.0, 20.0). "
                      "Bring:", row)  # both are in Alliance capitals: no Nearby line
        self.assertNotIn("Nearby", row)

    def test_instance_trainer_row(self):
        from yap_forever.planner import Plan, Step
        p = Plan(steps=[Step(333, 1, 300, 2, "Ench basic", 299, 0, 0, {toy.ROD: 299})], ranks=[(333, 250, 300, 450)],
                 events=["Enchanting 250: train rank up to 300 (4s 50c)"], final_skill={333: 300})
        text = render_guide(p, toy.gamedata(base_recipes()), toy.market(BARS), toy.stock(skills={333: 1}),
                            caps={333: 300}, trainer_info=self.info("horde"))
        (row,) = self.lines(text, "- **Trip:**")
        self.assertTrue(row.startswith("- **Trip:** Enchanting rank to 300: Zarn Runeweaver, inside Uldaman."), row)
        self.assertNotIn("(-1", text)

    def test_no_trainer_for_the_faction_says_so(self):
        text = self.route([(60, 150), (200, 225)], faction="horde")
        (row,) = [l for l in self.lines(text, "- **Trip:**") if "rank to 225" in l]
        self.assertIn("the planner has no Artisan Blacksmith trainer for your faction in its data.", row)
        self.assertNotIn("(-1", text)

    def test_expert_row_is_in_city_and_not_a_trip(self):
        text = self.route([(60, 150)], faction="horde")
        (row,) = self.lines(text, "- Train ")
        self.assertEqual(row, "- Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                              "(for example Grom Anvilhand, Orgrimmar).")
        self.assertEqual(self.lines(text, "- **Trip:**"), [])
        self.assertLess(text.index("At 60: train rank up to 150"), text.index(row))

    def test_expert_row_without_a_trainer_for_the_faction(self):
        text = self.route([(60, 150)], faction="alliance")
        (row,) = self.lines(text, "- Train ")
        self.assertIn("the planner has no Expert Blacksmith trainer for your faction in its data.", row)

    CLAUSE = "the town may have no auction house, mailbox or bank"

    def trip_row(self, text, what):
        (row,) = [l for l in self.lines(text, "- **Trip:**") if what in l]
        self.assertIn("Bring:", row)
        return row

    def test_bring_clause_dropped_for_a_capital_trainer(self):
        row = self.trip_row(self.route([(60, 150), (200, 225)]), "rank to 225")
        self.assertNotIn(self.CLAUSE, row)
        self.assertTrue(row.endswith("buy and collect before you go."), row)

    def test_bring_clause_dropped_when_the_nearby_line_is_printed(self):
        row = self.trip_row(self.route([(60, 150), (200, 225), (275, 300)]), "rank to 300")
        self.assertIn("Nearby:", row)
        self.assertNotIn(self.CLAUSE, row)

    def test_bring_clause_kept_when_nothing_better_is_known(self):
        for faction in ("", "horde"):  # no faction; and no Artisan trainer for the faction in the data
            row = self.trip_row(self.route([(60, 150), (200, 225)], faction=faction), "rank to 225")
            self.assertIn(self.CLAUSE, row, faction)

    def test_bring_clause_kept_for_an_instance_trainer(self):
        from yap_forever.planner import Plan, Step
        p = Plan(steps=[Step(333, 1, 250, 2, "Ench basic", 249, 0, 0, {toy.ROD: 249}),
                        Step(333, 250, 300, 22, "Ench two", 50, 0, 0, {toy.ROD: 50})],
                 ranks=[(333, 250, 300, 450)], bought={toy.ROD: 299},
                 events=["Enchanting 250: train rank up to 300 (4s 50c)"], final_skill={333: 300})
        gd = toy.gamedata(base_recipes() + [toy.recipe(22, "Ench two", 333, {toy.ROD: 1})])
        text = render_guide(p, gd, toy.market(BARS), toy.stock(skills={333: 1}),
                            caps={333: 300}, trainer_info=self.info("horde"))
        row = self.trip_row(text, "rank to 300")
        self.assertIn("inside Uldaman", row)
        self.assertIn(self.CLAUSE, row)

    def test_no_faction_is_todays_text(self):
        with_none = self.route([(60, 150), (200, 225), (275, 300)], faction="")
        self.assertEqual(self.lines(with_none, "- Train "), [])
        for row in self.lines(with_none, "- **Trip:**"):
            self.assertIn("the trainer is in a set town (the planner doesn't say where yet)", row)
        self.assertNotIn("Nearby", with_none)

    def test_missing_data_note_comes_once_near_the_top(self):
        text = self.route([(60, 150), (200, 225)], faction="", trainer_note="Trainer names are left out of this "
                                                                           "guide: the trainer data files are missing.")
        self.assertEqual(text.count("Trainer names are left out"), 1)
        self.assertLess(text.index("Trainer names are left out"), text.index("## Keep while levelling"))
        self.assertIn("set town", text)

    def test_faction_note_shown_to_its_faction(self):
        from yap_forever import trainer_notes
        from yap_forever.trainer_notes import Notes
        brikk = trainer_notes.load_notes().trainers[2836]  # the shipped note, on the fixture's Master Blacksmith
        notes = Notes({90001: brikk}, {})
        ranks = [(60, 150), (200, 225), (275, 300)]
        for faction, said, hidden in (("alliance", "A long first trip for Alliance.", "Horde"),
                                      ("horde", None, "Alliance")):
            (row,) = [l for l in self.lines(self.route(ranks, faction=faction, notes=notes), "- **Trip:**")
                      if "rank to 300" in l]
            self.assertIn("A safe neutral town.", row)
            self.assertNotIn(hidden, row)
            if said:
                self.assertIn("A safe neutral town. " + said, row)
            else:
                self.assertNotIn("long first trip", row)


class KeepGreensGuideTests(unittest.TestCase):
    def test_kept_green_row_says_keep_for_disenchanting(self):
        import dataclasses
        from yap_forever.planner import Plan, Step
        rs = [toy.recipe(3, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1))]
        st = Step(BS, 1, 10, 3, "BS belt", 9, 0, 0, {toy.COPPER_BAR: 9}, buffered=9)
        p = Plan(steps=[st], leftovers={toy.BELT: 9}, kept_greens={toy.BELT: 9}, final_skill={BS: 10})
        text = render_guide(p, toy.gamedata(rs), toy.market(BARS),
                            dataclasses.replace(toy.stock(), keep_greens=True), caps={BS: 10})
        row = next(l for l in text.splitlines() if "BS belt" in l and l.startswith("- **"))
        self.assertIn("keep for disenchanting on another character", row)


class WholeCraftGuideTests(unittest.TestCase):
    def test_range_line_counts_whole_crafts(self):
        from yap_forever.planner import Plan, Step
        gd = toy.gamedata(base_recipes() + [toy.recipe(10, "LW basic", LW, {toy.COPPER_BAR: 2})])
        st = Step(LW, 1, 100, 10, "LW basic", 133.4, 0, 0, {toy.COPPER_BAR: 266.8})
        st.buffered = st.crafts
        p = Plan(steps=[st], final_skill={LW: 100})
        text = render_guide(p, gd, toy.market(BARS), toy.stock(), caps={LW: 100})
        self.assertIn("134× LW basic — 268 Copper Bar", text)
        keep = text[text.index("## Keep while levelling"):text.index("## Route")]
        self.assertIn("268", keep)

    def test_row_names_the_intermediate_to_craft_first(self):
        from yap_forever.guide import render_guide
        from yap_forever.planner import Plan, Step
        S, T, L = toy.COPPER_BAR, toy.IRON_BAR, toy.ROD
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 2)), toy.recipe(42, "Make G", BS, {L: 1, T: 1})])
        st = Step(BS, 1, 4, 42, "Make G", 3, 0, 0, {T: 3}, buffered=3)
        p = Plan(steps=[st], crafted={L: 3}, final_skill={BS: 4})
        text = render_guide(p, gd, toy.market(), toy.stock(), caps={BS: 4})
        line = next(l for l in text.splitlines() if "× Make G" in l)
        self.assertIn("first craft 3 Copper Rod", line)
        self.assertIn("6 Copper Bar", line)


class TalentLineTests(unittest.TestCase):
    OVERTIME_RELATIVE = ("Working Overtime 5/5, read as +20% of the base chance (unconfirmed in game; "
                         'set working_overtime_reading = "points" for +20 percentage points).')
    OVERTIME_POINTS = "Working Overtime 5/5, read as +20 percentage points (unconfirmed in game)."

    def render(self, character=None, reading="relative", skills=None, caps=None):
        rs = base_recipes()
        st = toy.stock(skills=skills)
        caps = caps or {BS: 40, ENCH: 40}
        gd = toy.gamedata(rs)
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        overtime = character.working_overtime if character else 0
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps=caps, overtime=overtime,
                 reading=reading)
        return render_guide(p, gd, toy.market(BARS), st, caps=caps, character=character, reading=reading)

    def test_no_talents_no_lines(self):
        from yap_forever.profile import Character
        for c in (None, Character("A B"), Character("A B", working_overtime=0)):
            text = self.render(c)
            self.assertNotIn("Working Overtime", text)
            self.assertNotIn("Dedicated Study", text)

    def test_overtime_line_both_readings(self):
        from yap_forever.profile import Character
        c = Character("A B", working_overtime=5)
        self.assertIn(self.OVERTIME_RELATIVE, self.render(c, "relative"))
        text = self.render(c, "points")
        self.assertIn(self.OVERTIME_POINTS, text)
        self.assertNotIn("+20%", text)

    def test_overtime_line_names_the_rank(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", working_overtime=2))
        self.assertIn("Working Overtime 2/5, read as +8% of the base chance", text)

    def test_overtime_line_is_in_the_header_before_the_route(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", working_overtime=5))
        self.assertLess(text.index("Working Overtime 5/5"), text.index("## Keep while levelling"))

    def test_dedicated_study_names_the_lowest_profession(self):
        from yap_forever.profile import Character
        # Enchanting starts lower (skill 10 vs 30), so its remaining points count: 40 - 10 = 30.
        text = self.render(Character("A B", dedicated_study=True), skills={BS: 30, ENCH: 10})
        self.assertIn("Dedicated Study: one free point a day goes to your lowest profession; "
                      "30 days would cover the last 30 points of Enchanting.", text)
        self.assertNotIn("Working Overtime", text)

    def test_dedicated_study_tie_takes_the_first_profession_of_the_route(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", dedicated_study=True), skills={BS: 10, ENCH: 10})
        self.assertIn("last 30 points of Blacksmithing.", text)

    def test_dedicated_study_single_profession(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", dedicated_study=True), caps={ENCH: 25})
        self.assertIn("24 days would cover the last 24 points of Enchanting.", text)

    def test_dedicated_study_one_point_is_singular(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", dedicated_study=True), caps={ENCH: 2})
        self.assertIn("Dedicated Study: one free point a day goes to your lowest profession; "
                      "1 day would cover the last point of Enchanting.", text)
        self.assertNotIn("1 point", text)

    def test_dedicated_study_nothing_to_level(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", dedicated_study=True), skills={BS: 40, ENCH: 40})
        self.assertIn("Dedicated Study: one free point a day goes to your lowest profession; "
                      "Blacksmithing needs no points on this route.", text)

    def test_dedicated_study_off_has_no_line(self):
        from yap_forever.profile import Character
        text = self.render(Character("A B", dedicated_study=False), skills={BS: 30, ENCH: 10})
        self.assertNotIn("Dedicated Study", text)


class BudgetLineTests(unittest.TestCase):
    def render(self, next_stop, order=None):
        from yap_forever import budget
        from yap_forever.config import Budget
        rs = base_recipes()
        p = run(rs, BARS, cap=225)
        cut = budget.BudgetCut({BS: 225, ENCH: 225}, p, 341200, next_stop, {}, {BS: 225, ENCH: 225}, {BS: 1, ENCH: 1})
        goal = Budget(30, order)
        return render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(), {BS: 225, ENCH: 225},
                            budget_lines=budget.lines(cut, goal), order=order)

    def test_budget_lines(self):
        from yap_forever.guide import gold
        text = self.render({BS: (300, 1200000)})
        header = text[:text.index("## Route")]
        self.assertIn(f"30g takes Blacksmithing to 225 and Enchanting to 225 ({gold(341200)}).", header)
        self.assertIn(f"The next stop, Blacksmithing 300, costs about {gold(1200000)} more.", header)
        self.assertNotIn("The next stop", self.render({}))

    def test_one_at_a_time_intro(self):
        self.assertIn("Level one profession at a time: Enchanting first, then Blacksmithing.",
                      self.render({}, order=(ENCH, BS)))
        self.assertIn("Level both professions side by side", self.render({}))


class VisitRowTests(unittest.TestCase):
    """Trainer visits: the recipes learned at each, recipe trips and the recipes to know before starting."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        from yap_forever import trainers
        cls.data = trainers.load_trainer_data(Path(__file__).parent / "fixtures" / "gamedata")

    def render(self, start, ranks, recipes, learns, faction="alliance", data=None, alts=None, final=300,
               trainer_trips="as_needed", listed=None):
        """A Blacksmithing guide from `start`: ranks (skill, cap); recipes (spell, required skill, fee in copper);
        learns (spell, skill the route learns it at); listed: spell -> the skill the Forever data lists it from."""
        from yap_forever.planner import Plan, Step
        from yap_forever.trainer_text import TrainerInfo
        rs = base_recipes() + [toy.recipe(spell, f"Recipe {spell}", BS, {toy.COPPER_BAR: 1}, req=req, fee=fee)
                               for spell, req, fee in recipes]
        p = Plan(steps=[Step(BS, start, final, 1, "BS basic", final - start, 0, 0, {toy.COPPER_BAR: final - start})],
                 bought={toy.COPPER_BAR: final - start}, ranks=[(BS, s, cap, 450) for s, cap in ranks],
                 learn_log=[(BS, s, spell, "trainer") for spell, s in learns],
                 events=[f"Blacksmithing {s}: train rank up to {cap} (4s 50c)" for s, cap in ranks]
                 + [f"Blacksmithing {s}: Learn Recipe {spell} (trainer 1s)" for spell, s in learns],
                 final_skill={BS: final})
        info = TrainerInfo(faction, data or self.data) if faction else None
        rs = [dataclasses.replace(r, listed_skill=listed[r.spell_id]) if r.spell_id in (listed or {}) else r for r in rs]
        return render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(skills={BS: start}),
                            caps={BS: final}, alts=alts, trainer_info=info, trainer_trips=trainer_trips)

    def row(self, text, start, has):
        (row,) = [line for line in text.splitlines() if line.startswith(start) and has in line]
        return row

    def test_visit_row_lists_recipes(self):
        text = self.render(160, [(200, 225)], [(11, 170, 1000), (12, 180, 2500)], [(11, 205), (12, 215)], final=225)
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn("Or Wandering Smith, Ironforge (20.0, 20.0). While there, learn: Recipe 11 (10s 0c), "
                      "Recipe 12 (25s 0c).", row)
        self.assertNotIn("your skill allows", text)

    def test_visit_row_fees_keep_their_copper(self):  # as the route's "(trainer 4s 50c)" rows
        text = self.render(160, [(200, 225)], [(11, 170, 450), (12, 180, 2250), (13, 175, 90)],
                           [(11, 205), (12, 215), (13, 216)], final=225)
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn("While there, learn: Recipe 11 (4s 50c), Recipe 12 (22s 50c), Recipe 13 (0s 90c).", row)

    def test_if_missing_line(self):
        text = self.render(190, [(225, 300)], [(13, 180, 1000), (14, 185, 1000)], [(13, 230), (14, 240)])
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertTrue(row.endswith(" If you don't have them yet: Recipe 13, Recipe 14."), row)
        self.assertNotIn("While there", row)
        self.assertNotIn("Before you start", text)

    def test_before_start_line(self):  # RF3
        text = self.render(184, [(225, 300)], [(17, 160, 1000)], [(17, 184)])
        self.assertIn("- **Before you start**, make sure you know: Recipe 17 (any Artisan Blacksmith teaches it).",
                      text)
        route = text[text.index("## Route"):]
        self.assertLess(route.index("Before you start"), route.index("- **184–"))
        self.assertNotIn("Recipe 17", self.row(text, "- **Trip:**", "rank to 300"))

    def test_recipe_trip_has_skip_alternative(self):
        text = self.render(225, [(225, 300)], [(18, 240, 3000), (19, 245, 3000)], [(18, 240), (19, 251)],
                           alts={(18,): 30000, (19,): None})
        self.assertIn("- **Trip:** back to Brakka Ironfold, Stranglethorn Vale (30.0, 70.0), at 240 for Recipe 18 "
                      "(30s 0c); or skip it: +3.0g for the route without it.", text)
        self.assertIn("- **Trip:** back to Brakka Ironfold, Stranglethorn Vale (30.0, 70.0), at 251 for Recipe 19 "
                      "(30s 0c); there is no other way to reach the target without it.", text)
        route = text[text.index("## Route"):]
        self.assertLess(route.index("at 240 for"), route.index("at 251 for"))

    def test_visit_without_trainer_data(self):  # RF5
        from yap_forever import trainers
        data = trainers.TrainerData([trainers.Trainer(1, "Grom Anvilhand", BS, "Expert", "H", 1637, (80, 20), True)],
                                    {}, [], {1637: "Orgrimmar"})
        text = self.render(200, [(225, 300)], [(13, 210, 1000), (18, 240, 1000)], [(13, 230), (18, 240)],
                           faction="horde", data=data)
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn("the planner has no Master Blacksmith trainer for your faction in its data. While there, learn: "
                      "Recipe 13 (10s 0c).", row)
        self.assertIn("- **Trip:** back to the Master Blacksmith (the planner has no Master Blacksmith trainer for "
                      "your faction in its data), at 240 for Recipe 18 (10s 0c).", text)
        text = self.render(200, [(225, 300)], [(13, 210, 1000), (18, 240, 1000)], [(13, 230), (18, 240)], faction="")
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn("(the planner doesn't say where yet). While there, learn: Recipe 13 (10s 0c)", row)
        self.assertIn("- **Trip:** back to the Master Blacksmith in a set town (the planner doesn't say where yet), "
                      "at 240 for Recipe 18 (10s 0c).", text)

    def test_city_visit_rows(self):
        from yap_forever import trainers
        data = trainers.TrainerData([trainers.Trainer(1, "Grom Anvilhand", BS, "Expert", "H", 1637, (80, 20), True)],
                                    {}, [], {1637: "Orgrimmar"})
        text = self.render(100, [(130, 150)], [(20, 120, 500), (21, 140, 500)], [(20, 135), (21, 142)],
                           faction="horde", data=data, final=150)
        self.assertIn("- Train Blacksmithing to 150 at any Expert Blacksmith in a capital (for example Grom Anvilhand, "
                      "Orgrimmar). While there, learn: Recipe 20 (5s 0c).", text)
        self.assertIn("- At 142, learn Recipe 21 (5s 0c) at any Expert Blacksmith in a capital.", text)  # the rank row named them

    def grom(self):
        from yap_forever import trainers
        return trainers.TrainerData([trainers.Trainer(1, "Grom Anvilhand", BS, "Expert", "H", 1637, (80, 20), True)],
                                    {}, [], {1637: "Orgrimmar"})

    def test_learned_recipe_row_says_where_it_was_learned(self):
        text = self.render(184, [(225, 300)], [(17, 160, 1000), (13, 210, 2000), (18, 240, 3000)],
                           [(17, 184), (13, 230), (18, 240)])
        self.assertIn("- *At 184: start crafting Recipe 17 (learned before you start)*", text)
        self.assertIn("- *At 230: start crafting Recipe 13 (learned at Brakka Ironfold)*", text)
        self.assertIn("- *At 240: start crafting Recipe 18 (learned at Brakka Ironfold)*", text)
        self.assertNotIn("Learn Recipe", text)  # no second fee
        route = text[text.index("## Route"):]
        self.assertLess(route.index("at 240 for Recipe 18"), route.index("At 240: start crafting"))  # after the trip

    def test_capital_stops_after_the_first_are_short(self):
        from yap_forever.trainer_notes import Notes
        from yap_forever.trainer_text import TrainerInfo
        from yap_forever.planner import Plan, Step
        rs = base_recipes() + [toy.recipe(s, f"Recipe {s}", BS, {toy.COPPER_BAR: 1}, req=r, fee=500)
                               for s, r in ((20, 110), (21, 125), (22, 140))]
        p = Plan(steps=[Step(BS, 100, 150, 1, "BS basic", 50, 0, 0, {toy.COPPER_BAR: 50})], bought={toy.COPPER_BAR: 50},
                 learn_log=[(BS, 112, 20, "trainer"), (BS, 126, 21, "trainer"), (BS, 141, 22, "trainer")],
                 final_skill={BS: 150})
        info = TrainerInfo("horde", self.grom(), Notes({}, {1637: "A tip."}))
        text = render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(skills={BS: 100}), caps={BS: 150},
                            trainer_info=info)
        rows = [line for line in text.splitlines() if line.startswith("- At ") and ", learn " in line]
        self.assertEqual(rows, ["- At 112, learn Recipe 20 (5s 0c) at any Expert Blacksmith in a capital (for example "
                                "Grom Anvilhand, Orgrimmar). A tip.",
                                "- At 126, learn Recipe 21 (5s 0c) at any Expert Blacksmith in a capital.",
                                "- At 141, learn Recipe 22 (5s 0c) at any Expert Blacksmith in a capital."])

    def test_if_missing_on_a_recipe_trip_and_a_capital_stop(self):
        text = self.render(200, [], [(13, 210, 1000), (14, 190, 1000)], [(13, 212), (14, 220)])
        self.assertIn("- **Trip:** back to Thessa Hammerlow, Stormwind City (60.5, 40.2) or Wandering Smith, Ironforge "
                      "(20.0, 20.0), at 212 for Recipe 13 (10s 0c). If you don't have it yet: Recipe 14.", text)
        text = self.render(100, [], [(21, 140, 500), (23, 90, 500)], [(21, 142), (23, 145)], faction="horde",
                           data=self.grom(), final=150)
        self.assertIn("- At 142, learn Recipe 21 (5s 0c) at any Expert Blacksmith in a capital (for example Grom "
                      "Anvilhand, Orgrimmar). If you don't have it yet: Recipe 23.", text)

    def test_city_rank_row_without_a_faction(self):
        text = self.render(100, [(130, 150)], [(20, 120, 500)], [(20, 135)], faction="", final=150)
        self.assertIn("- Train Blacksmithing to 150 at any Expert Blacksmith in a capital. While there, learn: "
                      "Recipe 20 (5s 0c).", text)
        text = self.render(100, [(130, 150)], [], [], faction="", final=150)
        self.assertNotIn("- Train ", text)  # nothing to learn: no row, as before

    def test_recipe_trip_line_without_its_visit(self):
        from yap_forever.guide import _trip_line
        from yap_forever.trips import Trip
        line = _trip_line(Trip(240, BS, "recipe", "Recipe 18", cap=300, spells=(18,)), {(18,): None})
        self.assertEqual(line, "- **Trip:** back to the Master Blacksmith in a set town (the planner doesn't say where "
                               "yet), at 240 for Recipe 18; there is no other way to reach the target without it.")

    def test_one_go_lists_learn_skills(self):
        args = (225, [(225, 300)], [(18, 240, 3000), (19, 245, 3000)], [(18, 240), (19, 251)])
        text = self.render(*args, alts={(18,): 30000, (19,): None}, trainer_trips="one_go")
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn(" Learn at the trainer as you reach them: Recipe 18 at 240, Recipe 19 at 251.", row)
        self.assertNotIn("back to", text)
        self.assertIn("- *At 240: Learn Recipe 18 (trainer 1s)*", text)  # the fee, once
        self.assertIn("- *At 251: Learn Recipe 19 (trainer 1s)*", text)
        self.assertIn("back to Brakka Ironfold", self.render(*args))  # as needed: the trips back

    def test_one_go_learn_list_without_trainer_data(self):
        text = self.render(130, [(140, 225)], [(21, 145, 500), (22, 160, 500)], [(21, 146), (22, 170)], final=225,
                           trainer_trips="one_go")
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn(" Learn at the trainer as you reach them: Recipe 21 at 146, Recipe 22 at 170.", row)
        self.assertNotIn("in a capital", text[text.index("## Route"):].replace(row, ""))
        # without trainer data (no faction) the row still lists them
        text = self.render(130, [(140, 225)], [(21, 145, 500), (22, 160, 500)], [(21, 146), (22, 170)], final=225,
                           trainer_trips="one_go", faction="")
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn("(the planner doesn't say where yet). Learn at the trainer as you reach them: Recipe 21 at 146, "
                      "Recipe 22 at 170.", row)

    def test_one_go_skill_agrees_with_the_learn_row(self):
        text = self.render(225, [(225, 300)], [(18, 240, 1000), (19, 245, 1000), (20, 250, 1000)],
                           [(18, 240), (19, 251), (20, 270)], trainer_trips="one_go")
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn("Learn at the trainer as you reach them: Recipe 18 at 240, Recipe 19 at 251, Recipe 20 at 270.", row)
        self.assertIn("- *At 270: Learn Recipe 20 (trainer 1s)*", text)

    def test_no_fallback_clause(self):
        # a trainer teaches every recipe from 1 up to its rank's cap (confirmed in game, 2026-11-21): no row says
        # "if <trainer> doesn't list it", whatever the recipe's rank
        texts = [self.render(200, [(225, 300)], [(13, 210, 1000)], [(13, 230)]),  # Artisan recipe, Master visit
                 self.render(200, [(225, 300)], [(13, 210, 1000)], [(13, 230)], faction=""),
                 self.render(140, [(150, 225)], [(15, 145, 500), (16, 120, 500)], [(15, 160), (16, 170)], final=225),
                 self.render(130, [(140, 225)], [(21, 145, 500), (22, 160, 500)], [(21, 146), (22, 170)], final=225,
                             trainer_trips="one_go"),
                 self.render(60, [], [(21, 140, 500), (22, 74, 100)], [(21, 142), (22, 145)], faction="horde",
                             data=self.grom(), final=150)]
        for text in texts:
            self.assertNotIn("doesn't list", text)
            self.assertNotIn("Wandering Smith (Artisan", text)
        self.assertIn("While there, learn: Recipe 13 (10s 0c).", self.row(texts[0], "- **Trip:**", "rank to 300"))
        self.assertIn("- At 142, learn Recipe 21 (5s 0c), Recipe 22 (1s 0c) at any Expert Blacksmith in a capital (for "
                      "example Grom Anvilhand, Orgrimmar).", texts[4])

    def test_lists_keep_route_order(self):
        # Recipe 15 is an Expert recipe on an Artisan visit, Recipe 11 an Artisan one: they were grouped by rank
        # (the visit's own rank first); now "While there, learn:" lists them as the route learns them
        for learns, listed in (([(15, 205), (11, 215)], "Recipe 15 (5s 0c), Recipe 11 (10s 0c)"),
                               ([(11, 205), (15, 215)], "Recipe 11 (10s 0c), Recipe 15 (5s 0c)")):
            text = self.render(140, [(200, 225)], [(15, 145, 500), (11, 170, 1000)], learns, final=225)
            row = self.row(text, "- **Trip:**", "rank to 225")
            self.assertIn(f"While there, learn: {listed}.", row)

    def test_if_missing_pointer_is_conditional(self):
        args = (190, [(225, 300)], [(13, 180, 1000), (14, 185, 1000)], [(13, 230), (14, 240)])
        text = self.render(*args)
        self.assertIn("- *At 230: start crafting Recipe 13 (learn it at Brakka Ironfold if you don't have it)*", text)
        self.assertIn("- *At 240: start crafting Recipe 14 (learn it at Brakka Ironfold if you don't have it)*", text)
        self.assertNotIn("learned at", text)
        text = self.render(*args, listed={13: 170})
        self.assertIn("- *At 230: start crafting Recipe 13 (learn it at Brakka Ironfold if you don't have it; listed "
                      "from 170 in the Forever data: if the trainer offers it then, you can start it earlier)*", text)

    def test_learned_ahead_pointer_unchanged(self):
        text = self.render(184, [(225, 300)], [(13, 210, 2000)], [(13, 230)], listed={13: 200})
        self.assertIn("- *At 230: start crafting Recipe 13 (learned at Brakka Ironfold; listed from 200 in the "
                      "Forever data: if the trainer offers it then, you can start it earlier)*", text)
        text = self.render(184, [(225, 300)], [(13, 210, 2000)], [(13, 230)])
        self.assertIn("- *At 230: start crafting Recipe 13 (learned at Brakka Ironfold)*", text)

    def test_capital_stop_names_skill(self):
        text = self.render(60, [], [(21, 140, 500), (22, 74, 100)], [(21, 142), (22, 145)], faction="horde",
                           data=self.grom(), final=150)
        self.assertIn("- At 142, learn Recipe 21 (5s 0c), Recipe 22 (1s 0c) at any Expert Blacksmith in a capital "
                      "(for example Grom Anvilhand, Orgrimmar).", text)
        text = self.render(60, [], [(21, 140, 500)], [(21, 142)], faction="")
        self.assertIn("- At 142, learn Recipe 21 (5s 0c) at any Expert Blacksmith in a capital.", text)

    def test_free_skip_left_on_the_route_says_nothing(self):
        # #90: a skip that costs nothing more is taken when it saves a visit (plan.take_free_skips); one left on the
        # route saves none, so its row offers nothing
        text = self.render(225, [(225, 300)], [(18, 240, 3000), (19, 245, 3000)], [(18, 240), (19, 251)],
                           alts={(18,): 0.5, (19,): -20})
        self.assertIn("(30s 0c).", self.row(text, "- **Trip:**", "at 240 for"))
        self.assertIn("(30s 0c).", self.row(text, "- **Trip:**", "at 251 for"))
        self.assertNotIn("skip it", text)
        text = self.render(225, [(225, 300)], [(18, 240, 3000)], [(18, 240)], alts={(18,): 0.51})
        self.assertIn("(30s 0c); or skip it: +1c for the route without it.", self.row(text, "- **Trip:**", "at 240"))

    def test_free_skip_line(self):
        from yap_forever.guide import free_skip_line
        from yap_forever.trainer_text import TrainerInfo
        from yap_forever.trips import Trip
        gd = toy.gamedata(base_recipes() + [toy.recipe(18, "Recipe 18", BS, {toy.COPPER_BAR: 1}, req=240, fee=3000),
                                            toy.recipe(19, "Recipe 19", BS, {toy.COPPER_BAR: 1}, req=240, fee=3000)])
        trip = Trip(240, BS, "recipe", "Recipe 18, Recipe 19", cap=300, spells=(18, 19))
        self.assertEqual(free_skip_line(trip, gd, TrainerInfo("alliance", self.data)),
                         "Planned without the trip back to Brakka Ironfold at 240 for Recipe 18, Recipe 19: the route "
                         "without it costs the same.")
        self.assertEqual(free_skip_line(trip, gd), "Planned without the trip back to the Master Blacksmith at 240 for "
                                                   "Recipe 18, Recipe 19: the route without it costs the same.")
        for kind in ("vendor", "favor"):
            self.assertEqual(free_skip_line(Trip(230, BS, kind, "BS scroll", 30, 500), gd),
                             "Planned without the trip to buy the pattern for BS scroll: the route without it costs "
                             "the same.")

    def test_free_skip_lines_follow_the_saving_line(self):
        from yap_forever.planner import Plan
        line = "Planned without the trip back to the Master Blacksmith at 240 for Recipe 18: the route without it " \
               "costs the same."
        text = render_guide(Plan(final_skill={BS: 300}), toy.gamedata(base_recipes()), toy.market(BARS),
                            toy.stock(skills={BS: 225}), {BS: 300}, saving_line="A saving line.", free_skips=[line])
        head = text[:text.index("## ")]
        self.assertEqual(text.count(line), 1)
        self.assertLess(head.index("A saving line."), head.index(line))


class RunAcrossTrainingGuideTests(unittest.TestCase):
    def test_run_across_training_shows_in_both_stages(self):
        # #91: a run 210-244 with the Master training at 225 printed the whole run's count (51 on main) in both stages
        import math
        rs = [toy.recipe(1, "BS yellow", BS, {toy.COPPER_BAR: 2}, (toy.STONE, 1), t=(1, 200, 260, 320))]
        p, gd, m, st = toy.master_route_data(rs, toy.stock(skills={BS: 210}), cap=244)
        text = render_guide(p, gd, m, st, caps={BS: 244})
        stage3 = text[text.index("### Stage 3"):text.index("### Stage 4")]
        stage4 = text[text.index("### Stage 4"):]
        n1, n2 = (math.ceil(x.buffered - 1e-9) for x in p.steps)
        self.assertIn(f"- **210–225** · {n1}× BS yellow — {2 * n1} Copper Bar", stage3)
        self.assertIn(f"- **225–244** · {n2}× BS yellow — {2 * n2} Copper Bar", stage4)
        self.assertNotIn("225–244", stage3)
        self.assertNotIn("210–225", stage4)
        self.assertGreaterEqual(n1 + n2, 51)  # each part rounds up on its own: never fewer than the whole run
        self.assertNotIn("· 51× BS yellow", text)  # no row with the whole run's count
        self.assertEqual(text.count("× BS yellow"), 2)  # one row in each stage


class CouldAlsoMakeGuideTests(unittest.TestCase):
    """#95: the "You could also make" section comes after the route, before the shopping list."""
    BLOCK = ["## You could also make", "", "Merchant's Favor recipes to craft once ...", "",
             "- **Staff of Ana** (Enchanting 100, for level 30): 50 of your 150 Favor; materials about 10s on the AH.", ""]

    def test_section_after_route_before_shopping_list(self):
        p, gd, m, st = toy.master_route_data()
        text = render_guide(p, gd, m, st, caps={BS: 300}, could_make=self.BLOCK)
        self.assertEqual(text.count("## You could also make"), 1)
        self.assertLess(text.index("## Route"), text.index("## You could also make"))
        self.assertLess(text.index("## You could also make"), text.index("## Shopping list"))
        self.assertIn("\n".join(self.BLOCK), text)

    def test_no_section_without_suggestions(self):
        p, gd, m, st = toy.master_route_data()
        self.assertNotIn("You could also make", render_guide(p, gd, m, st, caps={BS: 300}))


IRONFORGE, DARNASSUS, UNDERCITY, ORGRIMMAR, THUNDER_BLUFF = 1537, 1657, 1497, 1637, 1638
DARNASSUS_TIP = "Most trainers are close together, but the bank and the AH are far apart."
UNDERCITY_TIP = ("The bank and the AH are in different parts of the city; there is a mailbox at the inn, a few steps "
                 "from the bank.")


def alliance_info(notes=None, ironforge_engineer=None):
    """Made-up Alliance trainers (tests/test_trainers.py capital_info) plus Expert Engineers in Ironforge
    (`ironforge_engineer`, default Fenn Sprocket) and Stormwind (Gil Coilspring)."""
    from yap_forever import trainers
    from yap_forever.trainer_notes import Notes
    from tests.test_trainers import capital_info
    fenn = ironforge_engineer or trainers.Trainer(9, "Fenn Sprocket", ENG, "Expert", "A", IRONFORGE, (70, 50), True)
    info = capital_info((fenn, trainers.Trainer(10, "Gil Coilspring", ENG, "Expert", "A", 1519, (62, 30), True)))
    return dataclasses.replace(info, notes=notes or Notes({}, {}))


class CapitalGuideTests(unittest.TestCase):
    """#98: the home capital's stage line and capital stops, the other capital's trips without bring lists, the line
    for two capitals, and the capitals' tips."""

    def info(self, faction="alliance", notes=None):
        """Made-up trainers (tests/test_trainers.py capital_info) plus Expert Engineers in Ironforge and Stormwind; with Horde, the
        Artisan Engineer in Orgrimmar, the Artisan Alchemist in Undercity and no Engineer in Thunder Bluff."""
        from yap_forever import trainers
        from yap_forever.trainer_notes import Notes
        T = trainers.Trainer
        if faction == "horde":
            ts = [T(1, "Vex Sourbrew", ALCH, "Artisan", "H", UNDERCITY, (48, 70), True),
                  T(2, "Grizz Boltwrench", ENG, "Artisan", "H", ORGRIMMAR, (75, 25), True),
                  T(3, "Rusk Gearjaw", ENG, "Expert", "H", ORGRIMMAR, (76, 24), True),
                  T(4, "Hana Hideweaver", 165, "Artisan", "H", THUNDER_BLUFF, (44, 45), True)]
            data = trainers.TrainerData(ts, {}, [], {UNDERCITY: "Undercity", ORGRIMMAR: "Orgrimmar",
                                                     THUNDER_BLUFF: "Thunder Bluff"})
            return TrainerInfo("horde", data, notes or Notes({}, {}))
        return alliance_info(notes)

    def render(self, home, trainer_trips="as_needed", info=None, alts=None, character=None, capitals=None,
               free_skips=(), **kw):
        """Engineering and Alchemy from 100 to 225: Engineering learns an Expert recipe at 118 (a capital stop), trains
        Artisan at 125 and goes back at 160 and 170; Alchemy trains Artisan at 130 and goes back at 197."""
        from yap_forever import trainer_text
        from yap_forever.planner import Plan, Step
        info = self.info() if info is None else (info or None)  # False: no trainer data
        rs = base_recipes() + [toy.recipe(61, "Eng basic", ENG, {toy.COPPER_BAR: 1}),
                               toy.recipe(62, "Alch basic", ALCH, {toy.COPPER_BAR: 1}),
                               toy.recipe(30, "Eng tube", ENG, {toy.COPPER_BAR: 1}, req=115, fee=100),
                               toy.recipe(31, "Eng strut", ENG, {toy.COPPER_BAR: 1}, req=155, fee=720),
                               toy.recipe(32, "Eng gizmo", ENG, {toy.COPPER_BAR: 1}, req=165, fee=810),
                               toy.recipe(41, "Alch elixir", ALCH, {toy.COPPER_BAR: 1}, req=190, fee=2880)]
        steps = [Step(ENG, 100, 125, 61, "Eng basic", 25, 0, 0, {toy.COPPER_BAR: 25}),
                 Step(ALCH, 100, 130, 62, "Alch basic", 30, 0, 0, {toy.COPPER_BAR: 30}),
                 Step(ENG, 125, 225, 61, "Eng basic", 100, 0, 0, {toy.COPPER_BAR: 100}),
                 Step(ALCH, 130, 225, 62, "Alch basic", 95, 0, 0, {toy.COPPER_BAR: 95})]
        ranks = [(ENG, 125, 225), (ALCH, 130, 225)]
        learns = [(ENG, 118, 30), (ENG, 160, 31), (ENG, 170, 32), (ALCH, 197, 41)]
        p = Plan(steps=steps, bought={toy.COPPER_BAR: 250}, ranks=[(q, s, c, 500) for q, s, c in ranks],
                 learn_log=[(q, s, spell, "trainer") for q, s, spell in learns],
                 events=[f"{PROFESSIONS[q]} {s}: train rank up to {c} (5s 0c)" for q, s, c in ranks]
                 + [f"{PROFESSIONS[q]} {s}: Learn {next(r.name for r in rs if r.spell_id == spell)} (trainer 1s)"
                    for q, s, spell in learns],
                 final_skill={ENG: 225, ALCH: 225})
        caps = trainer_text.stage_capitals(info) if capitals is None else capitals
        if home == "default":  # as plan.write_reports chooses it
            from yap_forever.plan import home_capital
            home = home_capital(caps, p, character, {ENG: 100, ALCH: 100})
        gd = toy.gamedata(rs)
        gd.trainer_ranks.update({ENG: gd.trainer_ranks[BS], ALCH: gd.trainer_ranks[BS]})
        return render_guide(p, gd, toy.market(BARS), toy.stock(skills={ENG: 100, ALCH: 100}),
                            caps={ENG: 225, ALCH: 225}, trainer_info=info, trainer_trips=trainer_trips, alts=alts,
                            character=character, capitals=caps, home=home, free_skips=free_skips, **kw)

    def rows(self, text, start, has=""):
        return [line for line in text.splitlines() if line.startswith(start) and has in line]

    def test_home_capital_visits_are_stops(self):
        for mode in ("as_needed", "one_go"):
            with self.subTest(mode=mode):
                text = self.render(IRONFORGE, mode)
                self.assertEqual(self.rows(text, "- **Trip:**", "Engineering"), [])
                self.assertEqual(self.rows(text, "- **Trip:**", "Bolt Cogsworth"), [])
                self.assertNotIn("Bring:", text)
                self.assertEqual(self.rows(text, "- At ", "in Ironforge:"),
                                 ["- At 125, in Ironforge: train Engineering to 225 at Bolt Cogsworth.",
                                  "- At 160, in Ironforge: learn Eng strut (7s 20c) at Bolt Cogsworth.",
                                  "- At 170, in Ironforge: learn Eng gizmo (8s 10c) at Bolt Cogsworth."])
                self.assertIn("**Engineering 125–225**\n\nLevel Engineering 125–225 in Ironforge: the Artisan Engineer "
                              "Bolt Cogsworth (68.5, 43.5) is there, with the AH, mailbox and bank.\n", text)
                self.assertIn("- *At 160: start crafting Eng strut (learned at Bolt Cogsworth)*", text)

    def test_other_capital_as_needed_and_one_go(self):
        said = " Darnassus has an AH, mailbox and bank: buy as you go there."
        text = self.render(IRONFORGE)
        self.assertEqual(self.rows(text, "- **Trip:**"),
                         ["- **Trip:** Alchemy rank to 225: Lira Moonleaf, Darnassus (55.0, 24.0)." + said,
                          "- **Trip:** back to Lira Moonleaf, Darnassus (55.0, 24.0), at 197 for Alch elixir (28s 80c)."
                          + said])
        self.assertNotIn("Level Alchemy", text)  # the other capital gets no stage line
        text = self.render(IRONFORGE, "one_go")
        self.assertEqual(self.rows(text, "- **Trip:**"),
                         ["- **Trip:** Alchemy rank to 225: Lira Moonleaf, Darnassus (55.0, 24.0). Learn at the trainer "
                          "as you reach them: Alch elixir at 197." + said])
        self.assertNotIn("Bring:", text)

    def test_remote_trips_unchanged(self):
        # a route with no capital stage (the Artisan Enchanter in Elwynn Forest): the same guide with or without them
        from yap_forever.planner import Plan, Step
        rs = base_recipes() + [toy.recipe(51, "Ench late", ENCH, {toy.ROD: 1}, req=180, fee=100)]
        p = Plan(steps=[Step(ENCH, 140, 150, 2, "Ench basic", 10, 0, 0, {toy.ROD: 10}),
                        Step(ENCH, 150, 225, 2, "Ench basic", 75, 0, 0, {toy.ROD: 75})],
                 bought={toy.ROD: 85}, ranks=[(ENCH, 150, 225, 500)], learn_log=[(ENCH, 200, 51, "trainer")],
                 events=["Enchanting 150: train rank up to 225 (5s 0c)", "Enchanting 200: Learn Ench late (trainer 1s)"],
                 final_skill={ENCH: 225})

        def guide(**kw):
            return render_guide(p, toy.gamedata(rs), toy.market({toy.ROD: [(100, 1000)]}), toy.stock(skills={ENCH: 140}),
                                caps={ENCH: 225}, trainer_info=self.info(), **kw)
        plain = guide()
        self.assertIn("- **Trip:** Enchanting rank to 225: Mara Runebright, Elwynn Forest (40.0, 50.0).", plain)
        self.assertIn("Bring:", plain)
        self.assertIn("- **Trip:** back to Mara Runebright", plain)
        from yap_forever import trainer_text
        self.assertEqual(guide(capitals=trainer_text.stage_capitals(self.info()), home=IRONFORGE), plain)

    def test_lower_rank_stop_names_the_home_capital(self):
        text = self.render(IRONFORGE)
        self.assertIn("- At 118, learn Eng tube (1s 0c) at any Expert Engineer in Ironforge.", text)
        # home Darnassus has no Engineer in the data: as before
        text = self.render(DARNASSUS)
        self.assertIn("- At 118, learn Eng tube (1s 0c) at any Expert Engineer in a capital (for example Fenn "
                      "Sprocket, Ironforge or Gil Coilspring, Stormwind City).", text)

    def test_two_capitals_line(self):
        line = ("This route's Artisan trainers are in Ironforge (Engineering) and Darnassus (Alchemy). This guide starts "
                "in Ironforge; to start in Darnassus, set capital = \"darnassus\" for this character in profile.toml.")
        text = self.render(IRONFORGE)
        head = text[:text.index("## Route")]
        self.assertIn("Level both professions side by side: craft in whichever one is lower.\n\n" + line + "\n", head)
        self.assertEqual(text.count(line), 1)
        from yap_forever.profile import Character
        set_ = self.render(IRONFORGE, character=Character("Ana Brightforge", capital="ironforge"))
        self.assertNotIn("This route's Artisan trainers", set_)  # the player chose: no line
        self.assertIn("This guide starts in Darnassus; to start in Ironforge, set capital = \"ironforge\"",
                      self.render(DARNASSUS))
        # the stages plan.write_reports found with the home (capital_stages) are the ones said, not found again
        self.assertNotIn("This route's", self.render(IRONFORGE, capital_stages={IRONFORGE: [(ENG, 225)]}))
        self.assertEqual(self.render(IRONFORGE, capital_stages={IRONFORGE: [(ENG, 225)], DARNASSUS: [(ALCH, 225)]}),
                         text)

    def test_skip_clause_on_capital_stop(self):
        text = self.render(IRONFORGE, alts={(31,): 30000, (32,): None, (41,): 4600})
        self.assertIn("- At 160, in Ironforge: learn Eng strut (7s 20c) at Bolt Cogsworth; or skip it: +3.0g for the "
                      "route without it.", text)
        self.assertIn("- At 170, in Ironforge: learn Eng gizmo (8s 10c) at Bolt Cogsworth; there is no other way to "
                      "reach the target without it.", text)
        self.assertIn("at 197 for Alch elixir (28s 80c); or skip it: +46s for the route without it. Darnassus has", text)

    def test_free_skip_line_for_a_stop(self):
        from yap_forever.guide import free_skip_line
        from yap_forever.trips import Trip, Visit
        gd = toy.gamedata([toy.recipe(32, "Eng gizmo", ENG, {toy.COPPER_BAR: 1}, req=165, fee=810)])
        visit = Visit(ENG, 170, 225, True, "recipe", [32], city=IRONFORGE)
        trip = Trip(170, ENG, "recipe", "Eng gizmo", cap=225, spells=(32,), visit=visit)
        self.assertEqual(free_skip_line(trip, gd, self.info(), IRONFORGE),
                         "Planned without the stop at 170 in Ironforge for Eng gizmo: the route without it costs the "
                         "same.")
        self.assertEqual(free_skip_line(trip, gd, self.info()),  # no home: the trip it is today
                         "Planned without the trip back to Bolt Cogsworth at 170 for Eng gizmo: the route without it "
                         "costs the same.")
        self.assertIn("Planned without the trip back to Bolt Cogsworth at 170",
                      free_skip_line(trip, gd, self.info(), DARNASSUS))

    def test_no_data_falls_back(self):  # RF2: no trainer data, or no faction: no stage capitals, so no home
        self.assertIn("Level Engineering", self.render("default"))  # the same route with both: a home
        for info in (None, TrainerInfo("", self.info().data)):
            with self.subTest(info=info):
                text = self.render("default", info=info or False)
                self.assertIn("- **Trip:** back to ", text)
                self.assertIn("- At 118, learn Eng tube (1s 0c) at any Expert Engineer in a capital.", text)
                self.assertNotIn("in Ironforge", text)
                self.assertNotIn("Level Engineering", text)
                self.assertNotIn("This route's", text)
                self.assertIn("Bring:", text)

    def test_horde_thunder_bluff_no_engineering(self):  # RF1
        text = self.render(THUNDER_BLUFF, info=self.info("horde"))
        self.assertIn("- At 118, learn Eng tube (1s 0c) at any Expert Engineer in a capital (for example Rusk Gearjaw, "
                      "Orgrimmar).", text)
        self.assertNotIn("in Thunder Bluff", text)
        self.assertIn("- **Trip:** Engineering rank to 225: Grizz Boltwrench, Orgrimmar (75.0, 25.0). Orgrimmar has an "
                      "AH, mailbox and bank: buy as you go there.", text)

    def test_city_tips(self):
        from yap_forever.trainer_notes import load_notes
        notes = load_notes()
        self.assertEqual(notes.cities[DARNASSUS], DARNASSUS_TIP)  # unchanged: no claim about mail
        self.assertEqual(notes.cities[UNDERCITY], UNDERCITY_TIP)
        text = self.render(DARNASSUS, info=self.info(notes=notes))
        self.assertIn("Level Alchemy 130–225 in Darnassus: the Artisan Alchemist Lira Moonleaf (55.0, 24.0) is there, "
                      "with the AH, mailbox and bank. " + DARNASSUS_TIP + "\n", text)
        text = self.render(IRONFORGE, info=self.info(notes=notes))  # a trip to Darnassus says it too
        self.assertIn("Darnassus has an AH, mailbox and bank: buy as you go there. " + DARNASSUS_TIP, text)
        text = self.render(UNDERCITY, info=self.info("horde", notes=notes))
        self.assertIn("Level Alchemy 130–225 in Undercity: the Artisan Alchemist Vex Sourbrew (48.0, 70.0) is there, "
                      "with the AH, mailbox and bank. " + UNDERCITY_TIP + "\n", text)

    def started(self, profs, home=None):
        """A guide for `profs` ((profession, start, ranks as (skill, cap)), each to its last cap) with the Artisan
        Blacksmith in Ironforge and the Artisan Alchemist in Darnassus; home: None for plan.home_capital's own."""
        from yap_forever import trainer_text, trainers
        from yap_forever.gamedata import Rank
        from yap_forever.plan import home_capital
        from yap_forever.planner import Plan, Step
        info = self.info()
        info = dataclasses.replace(info, data=dataclasses.replace(info.data, trainers=info.data.trainers + [
            trainers.Trainer(11, "Kord Anvilmane", BS, "Artisan", "A", IRONFORGE, (52, 41), True)]))
        spell = {BS: 1, ALCH: 62}
        rs = base_recipes() + [toy.recipe(62, "Alch basic", ALCH, {toy.COPPER_BAR: 1})]
        steps, ranks, final = [], [], {}
        for prof, start, trained in profs:
            final[prof] = trained[-1][1]
            cuts = [start] + [s for s, _c in trained if s > start] + [final[prof]]
            steps += [Step(prof, a, b, spell[prof], gd_name, b - a, 0, 0, {toy.COPPER_BAR: b - a})
                      for a, b in zip(cuts, cuts[1:]) if b > a
                      for gd_name in ["BS basic" if prof == BS else "Alch basic"]]
            ranks += [(prof, s, c, 500) for s, c in trained]
        p = Plan(steps=steps, bought={toy.COPPER_BAR: sum(s.crafts for s in steps)}, ranks=ranks,
                 events=[f"{PROFESSIONS[q]} {s}: train rank up to {c} (5s 0c)" for q, s, c, _f in ranks],
                 final_skill=final)
        gd = toy.gamedata(rs)
        master = Rank(300, 50000, 225, 35)
        gd.trainer_ranks.update({BS: gd.trainer_ranks[BS] + [master], ALCH: gd.trainer_ranks[BS] + [master]})
        stock = toy.stock(skills={prof: start for prof, start, _t in profs})
        caps = trainer_text.stage_capitals(info)
        if home is None:
            home = home_capital(caps, p, None, stock.skills)
        return render_guide(p, gd, toy.market(BARS), stock, caps=final, trainer_info=info, capitals=caps, home=home)

    def test_stage_trained_at_the_start_has_no_stage_line(self):
        # Blacksmithing at 225 (or 210) trains Master at once: no Ironforge stage, so no home and no "225–225" line,
        # even when another stage makes Ironforge the home
        for start in (225, 210):
            with self.subTest(start=start):
                text = self.started([(BS, start, [(start, 300)])])
                self.assertNotIn("Level Blacksmithing", text)
                self.assertNotIn("in Ironforge", text)
                forced = self.started([(BS, start, [(start, 300)])], home=IRONFORGE)
                self.assertNotIn(f"Level Blacksmithing {start}–{start}", forced)
        text = self.started([(BS, 225, [(225, 300)]), (ALCH, 225, [(225, 300)])])
        self.assertNotIn("This route's", text)  # neither capital is visited

    def test_levelled_stage_wins_over_a_stage_trained_at_the_start(self):
        # Blacksmithing at 225 trains Master at once; Alchemy levels 1–225: home Darnassus, Alchemy's visits are stops
        text = self.started([(BS, 225, [(225, 300)]), (ALCH, 1, [(50, 150), (130, 225)])])
        self.assertIn("Level Alchemy 130–225 in Darnassus: the Artisan Alchemist Lira Moonleaf (55.0, 24.0)", text)
        self.assertIn("- At 130, in Darnassus: train Alchemy to 225 at Lira Moonleaf.", text)
        self.assertNotIn("**Trip:** Alchemy", text)
        self.assertNotIn("This route's", text)


class JoinedStopGuideTests(unittest.TestCase):
    """#98: capital stops of the two professions close together on the route are one row in the first one's block
    (trips.join_stops), and the joined recipes' rows point at it."""

    def render(self, home=IRONFORGE, notes=None, reagent=None, items=None, bag_slots=None, later=(), eng=91, alts=None,
               reqs=None, ironforge_engineer=None):
        """Alchemy and Engineering 80–110 side by side, one point a step (Alchemy first at each skill), no buffer:
        a basic recipe to 91 (Engineering: to `eng`), then Alchemy crafts Alch draught (learned at 91 with Alch wisdom)
        and Engineering Eng contact (learned at `eng`, needs 85) to 110, one `reagent` each (default: Iron Bar, bought on
        the AH; Copper Rod is sold by a vendor, 20 to a stack). items: the bank. later: (profession, skill, spell) of
        further trainer recipes, learned and crafted from that skill on. reqs: spell -> required skill, over the
        defaults. ironforge_engineer: see alliance_info."""
        from yap_forever.planner import Plan, Step
        reagent = reagent or toy.IRON_BAR
        req = {71: 91, 72: 91, 73: 100, 81: 85, 82: 105, **(reqs or {})}
        rs = [toy.recipe(61, "Alch basic", ALCH, {reagent: 1}), toy.recipe(62, "Eng basic", ENG, {reagent: 1}),
              toy.recipe(71, "Alch draught", ALCH, {reagent: 1}, req=req[71], fee=405),
              toy.recipe(72, "Alch wisdom", ALCH, {reagent: 1}, req=req[72], fee=450),
              toy.recipe(73, "Alch later", ALCH, {reagent: 1}, req=req[73], fee=500),
              toy.recipe(81, "Eng contact", ENG, {reagent: 1}, req=req[81], fee=270),
              toy.recipe(82, "Eng late", ENG, {reagent: 1}, req=req[82], fee=300)]
        names = {r.spell_id: r.name for r in rs}
        learns = [(ALCH, 91, 71), (ALCH, 91, 72), (ENG, eng, 81), *later]

        def spell(prof, s):
            return max(((at, sp) for q, at, sp in learns if q == prof and at <= s and sp != 72),
                       default=(0, 61 if prof == ALCH else 62))[1]
        steps = [Step(prof, s, s + 1, spell(prof, s), names[spell(prof, s)], 1, 0, 0, {reagent: 1}, buffered=1)
                 for s in range(80, 110) for prof in (ALCH, ENG)]
        p = Plan(steps=steps, bought={toy.IRON_BAR: 60}, learn_log=[(q, s, sp, "trainer") for q, s, sp in learns],
                 events=[f"{PROFESSIONS[q]} {s}: Learn {names[sp]} (trainer 1s)" for q, s, sp in learns],
                 final_skill={ALCH: 110, ENG: 110})
        gd = toy.gamedata(rs)
        gd.items[toy.ROD] = dataclasses.replace(gd.items[toy.ROD], stack=20)
        gd.trainer_ranks.update({ENG: gd.trainer_ranks[BS], ALCH: gd.trainer_ranks[BS]})
        info = alliance_info(notes, ironforge_engineer)
        stock = toy.stock(items=items, skills={ALCH: 80, ENG: 80})
        stock.bag_slots = bag_slots
        return render_guide(p, gd, toy.market(BARS), stock, caps={ALCH: 110, ENG: 110}, trainer_info=info,
                            capitals={}, home=home, alts=alts)

    def test_joined_row(self):
        text = self.render()
        self.assertEqual([line for line in text.splitlines()
                          if "learn" in line and line.startswith("- ") and not line.startswith("- *At")],
                         ["- **Capital stop** at Alchemy 91 (in Ironforge): learn Alch draught (4s 5c), Alch wisdom "
                          "(4s 50c) at an Expert Alchemist, and Eng contact (2s 70c) at an Expert Engineer (you use it "
                          "from Engineering 91)."])
        self.assertIn("**Alchemy 80–110**\n\n- **80–91** · 11× Alch basic — 11 Iron Bar\n- **Capital stop** at Alchemy 91",
                      text)  # in A's block, at A's skill
        self.assertIn("- *At 91: start crafting Eng contact (learned at the capital stop at Alchemy 91)*", text)
        self.assertIn("- *At 91: start crafting Alch draught (learned at the Expert Alchemist)*", text)

    def test_join_in_any_capital_without_a_home(self):  # C27: say which city
        text = self.render(home=None)  # Ironforge is the first capital with an Expert Alchemist and Engineer
        self.assertIn("- **Capital stop** at Alchemy 91 (any capital, for example Ironforge): learn Alch draught", text)
        self.assertNotIn("Eng contact (2s 70c) at any", text)

    def test_different_parts_said_once(self):
        from yap_forever.trainer_notes import Notes
        apart = "In Ironforge, the Alchemy and Engineering trainers are in different parts of the city."
        text = self.render(notes=Notes({}, {}, {IRONFORGE: (frozenset({ALCH}), frozenset({ENG}))}),
                           later=[(ENG, 105, 82)])
        self.assertEqual(text.count(apart), 1)
        self.assertIn("(you use it from Engineering 91). " + apart, text)
        self.assertIn("- At 105, learn Eng late (3s 0c) at any Expert Engineer in Ironforge.\n", text)  # alone: as before

    def test_supply_vendor_sentence_counts(self):
        # the stop's rows to each profession's next visit: Alch draught 91–110 and Eng contact 91–110, 38 Copper Rod, less
        # the 8 the bank still holds after the basic rows; the second mailbox trip carries exactly these rows
        text = self.render(reagent=toy.ROD, items={toy.ROD: 30}, bag_slots=12)
        said = "The trade supplies vendor near the trainers sells the 30 Copper Rod these rows need."
        self.assertIn("(you use it from Engineering 91). " + said + "\n", text)
        (trip,) = [line for line in text.splitlines() if line.startswith("- 📬 **Trip 2** (skill 91–110")]
        self.assertIn(" From a vendor: 30 Copper Rod.", trip)
        self.assertIn(" From the bank: 8 Copper Rod.", trip)
        # Alchemy goes back at 100: its rows end there (Alch draught 91–100: 9, 8 of them from the bank), Engineering's
        # don't (19); the stop alone at 100 keeps its row, with no sentence; no bag slots: the sentence all the same
        text = self.render(reagent=toy.ROD, items={toy.ROD: 30}, later=[(ALCH, 100, 73)])
        self.assertIn("(you use it from Engineering 91). The trade supplies vendor near the trainers sells the 20 Copper "
                      "Rod these rows need.\n", text)
        self.assertIn("- At 100, learn Alch later (5s 0c) at any Expert Alchemist in Ironforge.\n", text)
        self.assertEqual(text.count("trade supplies"), 1)
        # Engineering joins from 95: its run 80–95, which the stop's skill falls in, is counted whole (15), then Eng
        # contact 95–110 (15) and Alch draught (19)
        text = self.render(reagent=toy.ROD, eng=95)
        self.assertIn("(you use it from Engineering 95). The trade supplies vendor near the trainers sells the 49 Copper "
                      "Rod these rows need.\n", text)

    def test_no_sentence_without_vendor_reagents(self):
        self.assertNotIn("trade supplies", self.render())  # Iron Bar comes from the AH
        self.assertNotIn("trade supplies", self.render(reagent=toy.ROD, items={toy.ROD: 200}))  # all in the bank

    def test_joined_row_keeps_the_first_stops_skip_clause(self):  # P34: the first stop's own, after its trainer
        text = self.render(alts={(71, 72): 30000, (81,): 4600})
        self.assertIn("at an Expert Alchemist; or skip it: +3.0g for the route without it, and Eng contact (2s 70c) at an "
                      "Expert Engineer (you use it from Engineering 91).\n", text)
        self.assertNotIn("+46s", text)

    def test_supply_sentences_add_up_across_two_joins(self):
        # Engineering's next stop after 91 is the one joined at Alchemy 100 (Engineering at 100 there, Eng late needs
        # 95): each row is in one sentence, so the two add up to what the mailbox trips buy from a vendor
        import re
        text = self.render(reagent=toy.ROD, items={toy.ROD: 22}, bag_slots=12, later=[(ALCH, 100, 73), (ENG, 105, 82)],
                           reqs={82: 95})
        self.assertIn("- **Capital stop** at Alchemy 100 (in Ironforge): learn Alch later (5s 0c) at an Expert Alchemist, "
                      "and Eng late (3s 0c) at an Expert Engineer (you use it from Engineering 105).", text)
        said = [int(n) for n in re.findall(r"supplies vendor near the trainers sells the (\d+) Copper Rod", text)]
        self.assertEqual(said, [9, 29])  # Alch draught 91–100; Alch later, Eng contact 91–105 and Eng late
        bought = [int(n) for n in re.findall(r"From a vendor: (\d+) Copper Rod", text)]
        self.assertEqual(sum(said), sum(bought))

    def test_joined_row_flags_an_unconfirmed_title(self):
        from yap_forever import trainers
        odd = trainers.Trainer(9, "Odd Tinker", ENG, "", "A", IRONFORGE, (70, 50), False)  # no rank in its title
        text = self.render(ironforge_engineer=odd)
        self.assertIn("at an Expert Alchemist, and Eng contact (2s 70c) at an Expert Engineer (title unconfirmed in the "
                      "data; you use it from Engineering 91).", text)

    def test_rank_training_takes_a_stop(self):
        # Engineering trains Artisan at 140 in Ironforge, its home stage (A); Alchemy's Expert stop at 145 for Alch
        # tonic (needs 135) joins it: Alchemy is at 141 there
        from yap_forever.planner import Plan, Step

        def text(eng_learns):
            rs = [toy.recipe(61, "Alch basic", ALCH, {toy.IRON_BAR: 1}), toy.recipe(62, "Eng basic", ENG, {toy.IRON_BAR: 1}),
                  toy.recipe(74, "Alch tonic", ALCH, {toy.IRON_BAR: 1}, req=135, fee=900),
                  toy.recipe(83, "Eng frame", ENG, {toy.IRON_BAR: 1}, req=140, fee=540)]
            steps = [Step(prof, s, s + 1, 61 if prof == ALCH else 62, "basic", 1, 0, 0, {toy.IRON_BAR: 1}, buffered=1)
                     for s in range(130, 160) for prof in (ALCH, ENG)]
            learns = [(ALCH, 145, 74)] + ([(ENG, 140, 83)] if eng_learns else [])
            p = Plan(steps=steps, bought={toy.IRON_BAR: 60}, ranks=[(ENG, 140, 225, 500)],
                     learn_log=[(q, s, sp, "trainer") for q, s, sp in learns],
                     events=["Engineering 140: train rank up to 225 (5s 0c)"],
                     final_skill={ALCH: 160, ENG: 160})
            gd = toy.gamedata(rs)
            gd.trainer_ranks.update({ENG: gd.trainer_ranks[BS], ALCH: gd.trainer_ranks[BS]})
            return render_guide(p, gd, toy.market(BARS), toy.stock(skills={ALCH: 130, ENG: 130}),
                                caps={ALCH: 160, ENG: 160}, trainer_info=alliance_info(),
                                capitals={(ENG, 225): IRONFORGE}, home=IRONFORGE)
        self.assertIn("- **Capital stop** at Engineering 140 (in Ironforge): train Engineering to 225 at an Artisan "
                      "Engineer, and learn Alch tonic (9s 0c) at an Expert Alchemist (you use it from Alchemy 145).\n",
                      text(False))
        # the rank training learns a recipe there too: one trainer per profession
        self.assertIn("- **Capital stop** at Engineering 140 (in Ironforge): train Engineering to 225 and learn Eng frame "
                      "(5s 40c) at an Artisan Engineer, and Alch tonic (9s 0c) at an Expert Alchemist (you use it from "
                      "Alchemy 145).\n", text(True))


class SellClauseGuideTests(unittest.TestCase):
    """#62: a route row says where its crafts are sold, by the one rule (`Valuer.ah_price`): on the AH up to the sale
    limit only when the AH pays well above a vendor. Pinned as the start of the clause (7b adds a vendor-back suffix)."""
    GEAR = 7777  # a made-up craft with a 1g vendor price

    def line(self, listing, quest=False, **stock):
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        gd = toy.gamedata([toy.recipe(1, "BS gear", 164, {toy.COPPER_BAR: 1}, (self.GEAR, 1))],
                          quest_items=[self.GEAR] if quest else ())
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        st = dataclasses.replace(toy.stock(), **stock)
        m = toy.market({**BARS, self.GEAR: [listing]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 20})
        text = render_guide(p, gd, m, st, {164: 20})
        return next(line for line in text.splitlines() if "× BS gear" in line)

    def test_route_row_sell_clauses(self):
        scarce, dead = (115790, 1), (13685, 50)  # net 11g and 1.3g at a 1g vendor price
        self.assertIn(" → sell up to 5 on the AH (about 11.0g each), the rest to a vendor", self.line(scarce))
        self.assertIn(" → sell to a vendor", self.line(dead))
        self.assertNotIn("AH", self.line(dead))
        self.assertIn(" → sell up to 3 on the AH (quest item, about 11.0g each), the rest to a vendor",
                      self.line(scarce, quest=True, quest_item_sales=3))
        self.assertIn(" → sell on the AH (quest item, about 11.0g each)", self.line(scarce, quest=True))
        self.assertIn(" → sell to a vendor", self.line(dead, quest=True))
        self.assertIn(" → sell up to 5 on the AH (about 1.3g each), the rest to a vendor",
                      self.line(dead, ah_premium=1.25))  # the setting moves the line

    def test_net_counts_vendor_sales_only(self):
        # #97 (C39): the Money section's Net counts crafts sold at their vendor price; "Back from selling crafts" is
        # every sale, AH included
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        gd = toy.gamedata([toy.recipe(1, "BS gear", 164, {toy.COPPER_BAR: 1}, (self.GEAR, 1))])
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        st, m = toy.stock(), toy.market({**BARS, self.GEAR: [(115790, 1)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 20})
        text = render_guide(p, gd, m, st, {164: 20})
        self.assertIn(f"- **Net:** about {gold(abs(p.economic_total))} profit (vendor sales only), "
                      "counting your bank and mined bars at what they would sell for.", text)

    def rows(self, listing, caps=100, sell=10000, t=(1, 300, 300, 300), **stock):
        """(the route rows of "BS gear", the plan) from Blacksmithing 1 to caps; sell: the gear's vendor price."""
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        gd = toy.gamedata([toy.recipe(1, "BS gear", 164, {toy.COPPER_BAR: 1}, (self.GEAR, 1), t=t)],
                          quest_items=[self.GEAR] if "quest_item_sales" in stock else ())
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=sell)
        st = dataclasses.replace(toy.stock(), **stock)
        m = toy.market({**BARS, self.GEAR: [listing]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: caps})
        text = render_guide(p, gd, m, st, {164: caps})
        return [line for line in text.splitlines() if "× BS gear" in line], p

    def test_route_row_cashback(self):
        # #97: a row whose crafts go to a vendor says about what they bring back: the vendor price x the row's crafts
        # (expected, in whole crafts) x the output, less the units sold on the AH, which go to the item's first rows.
        # The AH-only quest form says nothing more (C34)
        scarce, dead = (115790, 1), (13685, 50)  # net 11g and 1.3g at a 1g vendor price
        self.assertTrue(self.line(dead).endswith(" → sell to a vendor: about 19.0g back"), self.line(dead))
        self.assertTrue(self.line(scarce).endswith(" → sell up to 5 on the AH (about 11.0g each), the rest to a vendor: "
                                                   "about 14.0g back"), self.line(scarce))
        quest = self.line(scarce, quest=True, quest_item_sales=3)
        self.assertTrue(quest.endswith("(quest item, about 11.0g each), the rest to a vendor: about 16.0g back"), quest)
        self.assertTrue(self.line(scarce, quest=True).endswith(" → sell on the AH (quest item, about 11.0g each)"))
        # two rows of one craft (1-75, 75-100): the AH's 5 go to the first one
        (first, second), _p = self.rows(scarce)
        self.assertTrue(first.startswith("- **1–75** · 74× BS gear"), first)
        self.assertTrue(first.endswith("the rest to a vendor: about 69.0g back"), first)
        self.assertTrue(second.endswith("the rest to a vendor: about 25.0g back"), second)
        # the AH takes every one of the first row's crafts: that row says nothing more
        (first, second), _p = self.rows(scarce, quest_item_sales=80)
        self.assertTrue(first.endswith("(quest item, about 11.0g each), the rest to a vendor"), first)
        self.assertTrue(second.endswith("the rest to a vendor: about 19.0g back"), second)
        # a craft a vendor pays nothing for (RF3): no amount
        (row,), _p = self.rows((50, 50), caps=20, sell=0)
        self.assertTrue(row.endswith(" → sell to a vendor"), row)

    def test_row_cashback_adds_up_to_vendor_back(self):
        # C40: the rows count whole crafts and Money's "from vendors" (Plan.vendor_back) the expected units, every one at
        # its vendor price: they differ by less than one craft's vendor value a row, once the AH's units are added back.
        # Yellow and green points, so the buffer is in the rows' counts
        import re
        for listing, on_ah in (((150, 50), 0), ((1000, 50), 5)):  # a 1s vendor price: vendor only, then the AH's 5
            for caps, t in ((20, (1, 10, 15, 30)), (90, (1, 60, 80, 100))):
                with self.subTest(listing=listing, caps=caps):
                    rows, p = self.rows(listing, caps=caps, sell=100, t=t)
                    back = [int(m.group(1)) * 100 for r in rows if (m := re.search(r": about (\d+)s back$", r))]
                    self.assertEqual(len(back), len(rows))
                    self.assertGreater(sum(int(re.search(r"· (\d+)×", r).group(1)) for r in rows),
                                       sum(back) / 100 + on_ah)  # the rows ask for more crafts: the buffer
                    self.assertLessEqual(abs(sum(back) + on_ah * 100 - p.vendor_back), 100 * len(rows))

    def test_money_and_totals_lines(self):
        # #97: Money and the report's Totals say what vendors pay back (counted in choosing the route) and what AH sales
        # add on top (not counted); without AH sales the Money line has no AH clause
        from yap_forever.costmodel import Valuer, money
        from yap_forever.planner import plan
        from yap_forever.report import render, verdict
        gd = toy.gamedata([toy.recipe(1, "BS gear", 164, {toy.COPPER_BAR: 1}, (self.GEAR, 1))])
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        st = toy.stock()
        for listing in ((115790, 1), (13685, 50)):
            with self.subTest(listing=listing):
                m = toy.market({**BARS, self.GEAR: [listing]})
                p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 20})
                guide = render_guide(p, gd, m, st, {164: 20})
                report = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 20})
                self.assertAlmostEqual(p.vendor_back, 19 * 10000)
                if listing == (13685, 50):
                    self.assertEqual(p.ah_extra, 0)
                    self.assertIn("- **Back from selling crafts:** about 19.0g from vendors (counted in choosing the "
                                  "route).\n", guide)
                else:
                    self.assertGreater(p.ah_extra, 0)
                    self.assertIn(f"- **Back from selling crafts:** about {gold(p.sale_proceeds)}: 19.0g from vendors "
                                  f"(counted in choosing the route) and about {gold(p.ah_extra)} more if the AH sales go "
                                  "through.\n", guide)
                self.assertIn(f"- Back from vendors: {money(p.vendor_back)} (counted in choosing the route).\n", report)
                self.assertIn(f"- AH sales on top: {money(p.ah_extra)} (not counted).\n", report)
                self.assertNotIn("Expected sales", report)
