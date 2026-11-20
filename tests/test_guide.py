import dataclasses
import datetime
import unittest

from tests import toy
from yap_forever.gamedata import PROFESSIONS
from yap_forever.guide import render_guide, source_group
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


LINE = ("Prices: Auctionator scan of 2026-11-18 (one price per item, no listing depth: costs are a lower "
        "bound and AH sale limits are approximate).")


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
        self.assertIn("sell up to 20 on the AH (quest item), the rest to a vendor", text)


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
               trainer_trips="as_needed"):
        """A Blacksmithing guide from `start`: ranks (skill, cap); recipes (spell, required skill, fee in copper);
        learns (spell, skill the route learns it at)."""
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
        return render_guide(p, toy.gamedata(rs), toy.market(BARS), toy.stock(skills={BS: start}),
                            caps={BS: final}, alts=alts, trainer_info=info, trainer_trips=trainer_trips)

    def row(self, text, start, has):
        (row,) = [line for line in text.splitlines() if line.startswith(start) and has in line]
        return row

    def test_visit_row_lists_recipes(self):
        text = self.render(160, [(200, 225)], [(11, 170, 1000), (12, 180, 2500)], [(11, 205), (12, 215)], final=225)
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn("Or Wandering Smith, Ironforge (20.0, 20.0). While there, learn: Recipe 11 (10s), "
                      "Recipe 12 (25s).", row)
        self.assertNotIn("your skill allows", text)

    def test_if_missing_line(self):
        text = self.render(190, [(225, 300)], [(13, 180, 1000), (14, 185, 1000)], [(13, 230), (14, 240)])
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn(" If you don't have them yet: Recipe 13, Recipe 14 (if Brakka Ironfold doesn't list them: ", row)
        self.assertNotIn("While there", row)
        self.assertNotIn("Before you start", text)

    def test_fallback_names_lower_trainer(self):
        text = self.render(200, [(225, 300)], [(13, 210, 1000)], [(13, 230)])
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn("While there, learn: Recipe 13 (10s) (if Brakka Ironfold doesn't list it: Thessa Hammerlow "
                      "(Artisan, Stormwind City) or Wandering Smith (Artisan, Ironforge)).", row)
        # below the remote ranks the fallback is any trainer of the recipe's rank
        text = self.render(140, [(150, 225)], [(15, 145, 500), (16, 120, 500)], [(15, 160), (16, 170)], final=225)
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn("While there, learn: Recipe 15 (5s) (if the Artisan Blacksmith doesn't list it: any Expert "
                      "Blacksmith). If you don't have it yet: Recipe 16 (if the Artisan Blacksmith doesn't list it: "
                      "any Expert Blacksmith).", row)

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
                      "(30s); or skip it: +3.0g for the route without it.", text)
        self.assertIn("- **Trip:** back to Brakka Ironfold, Stranglethorn Vale (30.0, 70.0), at 251 for Recipe 19 "
                      "(30s); there is no other way to reach the target without it.", text)
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
                      "Recipe 13 (10s) (if the Master Blacksmith doesn't list it: any Artisan Blacksmith).", row)
        self.assertIn("- **Trip:** back to the Master Blacksmith (the planner has no Master Blacksmith trainer for "
                      "your faction in its data), at 240 for Recipe 18 (10s).", text)
        text = self.render(200, [(225, 300)], [(13, 210, 1000), (18, 240, 1000)], [(13, 230), (18, 240)], faction="")
        row = self.row(text, "- **Trip:**", "rank to 300")
        self.assertIn("(the planner doesn't say where yet). While there, learn: Recipe 13 (10s)", row)
        self.assertIn("- **Trip:** back to the Master Blacksmith in a set town (the planner doesn't say where yet), "
                      "at 240 for Recipe 18 (10s).", text)

    def test_city_visit_rows(self):
        from yap_forever import trainers
        data = trainers.TrainerData([trainers.Trainer(1, "Grom Anvilhand", BS, "Expert", "H", 1637, (80, 20), True)],
                                    {}, [], {1637: "Orgrimmar"})
        text = self.render(100, [(130, 150)], [(20, 120, 500), (21, 140, 500)], [(20, 135), (21, 142)],
                           faction="horde", data=data, final=150)
        self.assertIn("- Train Blacksmithing to 150 at any Expert Blacksmith in a capital (for example Grom Anvilhand, "
                      "Orgrimmar). While there, learn: Recipe 20 (5s).", text)
        self.assertIn("- Learn Recipe 21 (5s) at any Expert Blacksmith in a capital.", text)  # the rank row named them

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
        rows = [line for line in text.splitlines() if line.startswith("- Learn ")]
        self.assertEqual(rows, ["- Learn Recipe 20 (5s) at any Expert Blacksmith in a capital (for example Grom "
                                "Anvilhand, Orgrimmar). A tip.",
                                "- Learn Recipe 21 (5s) at any Expert Blacksmith in a capital.",
                                "- Learn Recipe 22 (5s) at any Expert Blacksmith in a capital."])

    def test_capital_stop_fallback_comes_after_the_place(self):
        # a Journeyman recipe (70) joins an Expert stop: its fallback note follows the place
        text = self.render(60, [], [(21, 140, 500), (22, 74, 100)], [(21, 142), (22, 145)], faction="horde",
                           data=self.grom(), final=150)
        self.assertIn("- Learn Recipe 21 (5s), Recipe 22 (1s) at any Expert Blacksmith in a capital (for example "
                      "Grom Anvilhand, Orgrimmar) (if the Expert Blacksmith doesn't list Recipe 22: any Journeyman "
                      "Blacksmith).", text)

    def test_if_missing_on_a_recipe_trip_and_a_capital_stop(self):
        text = self.render(200, [], [(13, 210, 1000), (14, 190, 1000)], [(13, 212), (14, 220)])
        self.assertIn("- **Trip:** back to Thessa Hammerlow, Stormwind City (60.5, 40.2) or Wandering Smith, Ironforge "
                      "(20.0, 20.0), at 212 for Recipe 13 (10s). If you don't have it yet: Recipe 14.", text)
        text = self.render(100, [], [(21, 140, 500), (23, 90, 500)], [(21, 142), (23, 145)], faction="horde",
                           data=self.grom(), final=150)
        self.assertIn("- Learn Recipe 21 (5s) at any Expert Blacksmith in a capital (for example Grom Anvilhand, "
                      "Orgrimmar). If you don't have it yet: Recipe 23.", text)

    def test_city_rank_row_without_a_faction(self):
        text = self.render(100, [(130, 150)], [(20, 120, 500)], [(20, 135)], faction="", final=150)
        self.assertIn("- Train Blacksmithing to 150 at any Expert Blacksmith in a capital. While there, learn: "
                      "Recipe 20 (5s).", text)
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

    def test_one_go_learn_list_names_the_fallback(self):
        text = self.render(130, [(140, 225)], [(21, 145, 500), (22, 160, 500)], [(21, 146), (22, 170)], final=225,
                           trainer_trips="one_go")
        row = self.row(text, "- **Trip:**", "rank to 225")
        self.assertIn(" Learn at the trainer as you reach them: Recipe 21 at 146 (if the Artisan Blacksmith doesn't "
                      "list it: any Expert Blacksmith), Recipe 22 at 170.", row)
        self.assertNotIn("in a capital", text[text.index("## Route"):].replace(row, ""))
