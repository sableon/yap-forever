"""The safe route: trainer recipes are planned at their inferred requirement, the Forever listing is
noted, the possible saving is named, and expensive stretches of the lowest profession point to
Dedicated Study."""
import tempfile
import unittest
from pathlib import Path

from tests import toy
from tests.test_planner import BARS, base_recipes
from yap_forever import gamedata, profile
from yap_forever.config import Goal
from yap_forever.costmodel import Valuer
from yap_forever.gamedata import safe_requirements
from yap_forever.guide import render_guide
from yap_forever.planner import Plan, Step, plan, resolve_goals

BS, ENCH = 164, 333
FIX = Path(__file__).parent / "fixtures" / "gamedata"
IRON = {toy.IRON_BAR: [(10, 100000)]}


def cheap_recipes(source="trainer", scroll=None, inferred=50, req=20):
    """BS basic always works; "BS cheap" (iron, a tenth of the price) is listed from `req`."""
    cheap = toy.recipe(3, "BS cheap", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), req=req, source=source, scroll=scroll)
    cheap.inferred_skill = inferred
    return base_recipes() + [cheap]


def run_plan(gd, cap=60, **kw):
    st = toy.stock()
    return plan(gd, Valuer(toy.market({**BARS, **IRON}), gd, st), st, toy.NO_FAVOR, caps={BS: cap}, **kw)


def learned_at(p, spell):
    return next((s for _prof, s, sp, _how in p.learn_log if sp == spell), None)


class SafeRequirementsTests(unittest.TestCase):
    def test_trainer_recipe_needs_the_higher_inferred_skill(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        r = gd.recipes[3]
        self.assertEqual((r.required_skill, r.listed_skill, r.inferred_skill), (50, 20, 50))

    def test_inferred_not_above_the_listing_changes_nothing(self):
        for inferred in (None, 20, 10):
            with self.subTest(inferred=inferred):
                r = safe_requirements(toy.gamedata(cheap_recipes(inferred=inferred))).recipes[3]
                self.assertEqual((r.required_skill, r.listed_skill), (20, None))

    def test_other_sources_are_unchanged(self):
        for source in ("scroll", "favor", "starter", "unknown", "quest"):
            with self.subTest(source=source):
                gd = safe_requirements(toy.gamedata(cheap_recipes(source=source, inferred=80)))
                self.assertEqual((gd.recipes[3].required_skill, gd.recipes[3].listed_skill), (20, None))

    def test_the_game_data_it_was_given_is_not_changed(self):
        gd = toy.gamedata(cheap_recipes())
        safe_requirements(gd)
        self.assertEqual((gd.recipes[3].required_skill, gd.recipes[3].listed_skill), (20, None))

    def test_applying_it_twice_keeps_the_forever_value(self):
        r = safe_requirements(safe_requirements(toy.gamedata(cheap_recipes()))).recipes[3]
        self.assertEqual((r.required_skill, r.listed_skill), (50, 20))

    def test_listed_requirements_undo_it(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        r = gamedata.listed_requirements(gd).recipes[3]
        self.assertEqual((r.required_skill, r.listed_skill), (20, None))
        self.assertEqual(gd.recipes[3].required_skill, 50)

    def test_loaded_fixture_recipe(self):
        gd = safe_requirements(gamedata.load_gamedata(FIX))
        self.assertEqual((gd.recipes[2661].required_skill, gd.recipes[2661].listed_skill), (35, 30))
        self.assertEqual((gd.recipes[2660].required_skill, gd.recipes[2660].listed_skill), (1, None))


class SafeRouteTests(unittest.TestCase):
    def test_listed_data_learns_the_trainer_recipe_early(self):  # the control for the next test
        p = run_plan(toy.gamedata(cheap_recipes()))
        self.assertEqual(learned_at(p, 3), 20)

    def test_trainer_recipe_is_not_learned_before_its_inferred_skill(self):
        p = run_plan(safe_requirements(toy.gamedata(cheap_recipes())))
        self.assertEqual(learned_at(p, 3), 50)
        self.assertEqual(p.final_skill, {BS: 60})
        for s in p.steps:
            if s.spell_id == 3:
                self.assertGreaterEqual(s.skill_from, 50)

    def test_a_scroll_recipe_with_an_inferred_value_is_unchanged(self):
        gd = toy.gamedata(cheap_recipes(source="scroll", scroll=toy.SCROLL, inferred=50))
        gd.vendor_prices[toy.SCROLL] = 5
        p = run_plan(safe_requirements(gd))
        self.assertEqual(learned_at(p, 3), 20)

    def test_a_recipe_goal_resolves_to_the_safe_requirement(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        self.assertEqual(resolve_goals({BS: Goal(recipe="BS cheap")}, gd), ({BS: 50}, {BS: 3}))
        listed = toy.gamedata(cheap_recipes())
        self.assertEqual(resolve_goals({BS: Goal(recipe="BS cheap")}, listed), ({BS: 20}, {BS: 3}))

    def test_plan_route_on_safe_data_learns_the_trainer_recipe_at_the_inferred_skill(self):
        from yap_forever.plan import PlanInputs, plan_route
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        p = plan_route(PlanInputs(gd=gd, market=toy.market({**BARS, **IRON}), stock=toy.stock(), favor=toy.NO_FAVOR,
                                  caps={BS: 60}, craft_once={}, quests={}), "gold")
        self.assertEqual(learned_at(p, 3), 50)


class ListedSavingTests(unittest.TestCase):
    def setUp(self):
        from yap_forever.compare import settle_routes
        from yap_forever.plan import PlanInputs, candidates
        self.settle_routes, self.candidates = settle_routes, candidates
        market, stock = toy.market({**BARS, **IRON}), toy.stock()
        self.inputs_for = lambda gd, m=market: PlanInputs(
            gd=gd, market=m, stock=stock, favor=toy.NO_FAVOR, caps={BS: 60}, craft_once={}, quests={})

    def routes(self, gd):
        return self.settle_routes(self.candidates(self.inputs_for(gd)), {BS: 60})[0]

    def test_saving_is_the_listed_routes_gap_in_each_routes_own_measure(self):
        from yap_forever.plan import listed_savings
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        safe = self.routes(gd)
        listed = self.routes(gamedata.listed_requirements(gd))
        got = listed_savings(self.inputs_for(gd), safe)
        self.assertEqual(got["gold"], safe["gold"].cash_total - listed["gold"].cash_total)
        self.assertEqual(got["value"], safe["value"].economic_total - listed["value"].economic_total)
        self.assertGreater(got["gold"], 100)

    def test_no_saving_when_the_listing_is_no_cheaper(self):
        from yap_forever.plan import listed_savings
        gd = safe_requirements(toy.gamedata(cheap_recipes(inferred=None)))
        self.assertEqual(listed_savings(self.inputs_for(gd), self.routes(gd)), {})
        dear = cheap_recipes()
        dear[-1].reagents = {toy.COPPER_BAR: 3}  # costlier than BS basic: the listing changes nothing
        gd = safe_requirements(toy.gamedata(dear))
        self.assertEqual(listed_savings(self.inputs_for(gd), self.routes(gd)), {})

    def test_a_gap_under_one_silver_gives_no_line(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        market = toy.market({**BARS, toy.IRON_BAR: [(99, 100000)]})  # iron 1c under copper: a tiny gap
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        inputs = self.inputs_for(gd, market)
        safe = self.settle_routes(self.candidates(inputs), {BS: 60})[0]
        self.assertEqual(plan_mod.listed_savings(inputs, safe), {})
        with mock.patch.object(plan_mod, "MIN_SAVING", 1):  # the same gap is there, only the floor hides it
            self.assertTrue(plan_mod.listed_savings(inputs, safe))

    def test_quest_recipes_are_left_alone_and_claim_no_saving(self):
        from yap_forever.plan import listed_savings
        gd = safe_requirements(toy.gamedata(cheap_recipes()), skip={3})
        self.assertEqual((gd.recipes[3].required_skill, gd.recipes[3].listed_skill), (20, None))
        self.assertEqual(listed_savings(self.inputs_for(gd), self.routes(gd)), {})

    def test_the_line_names_the_amount_in_guide_gold(self):
        from yap_forever.guide import gold
        from yap_forever.plan import saving_line
        self.assertEqual(
            saving_line(1_234_500),
            f"A route planned at the Forever listing (trainers offering recipes from their listed skill) "
            f"could cost about {gold(1_234_500)} less.")
        self.assertIn("123g", saving_line(1_234_500))


def toy_plan(cash_per_step, skills=((1, 11), (11, 21)), prof=BS):
    steps = [Step(prof, a, b, 1, "BS basic", b - a, c, c * 2, {toy.COPPER_BAR: b - a})
             for (a, b), c in zip(skills, cash_per_step)]
    return Plan(steps=steps, final_skill={prof: skills[-1][1]})


class GuideNotesTests(unittest.TestCase):
    def guide(self, p, gd, stock=None, caps=None, **kw):
        return render_guide(p, gd, toy.market(BARS), stock or toy.stock(skills={BS: 30}), caps or {BS: 60}, **kw)

    def learn_plan(self, gd, how="trainer"):
        steps = [Step(BS, 50, 60, 3, "BS cheap", 10, 0, 0, {toy.IRON_BAR: 10})]
        return Plan(steps=steps, learn_log=[(BS, 50, 3, how)], final_skill={BS: 60},
                    events=["Blacksmithing 50: Learn BS cheap (trainer 45s 0c)"])

    def test_learn_row_says_where_the_forever_data_lists_the_recipe(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        text = self.guide(self.learn_plan(gd), gd, toy.stock(skills={BS: 50}))
        (row,) = [l for l in text.splitlines() if l.startswith("- *At 50: Learn BS cheap")]
        self.assertEqual(row, "- *At 50: Learn BS cheap (trainer 45s 0c; listed from 20 in the Forever data: "
                              "if the trainer offers it then, you can start it earlier)*")

    def test_old_fallback_wording_is_gone(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes()))
        text = self.guide(self.learn_plan(gd), gd, toy.stock(skills={BS: 50}))
        for old in ("inferred", "isn't offered", "come back at", "instead"):
            self.assertNotIn(old, text)

    def test_no_note_on_a_recipe_that_was_not_raised(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes(inferred=None)))
        text = self.guide(self.learn_plan(gd), gd, toy.stock(skills={BS: 50}))
        self.assertNotIn("listed from", text)

    def test_no_note_on_a_recipe_learned_another_way(self):
        gd = safe_requirements(toy.gamedata(cheap_recipes(source="scroll", scroll=toy.SCROLL)))
        text = self.guide(self.learn_plan(gd, "vendor"), gd, toy.stock(skills={BS: 50}))
        self.assertNotIn("listed from", text)

    def test_the_saving_line_is_in_the_header_and_only_once(self):
        gd = toy.gamedata(base_recipes())
        text = self.guide(toy_plan([100]), gd, saving_line="If trainers offer a saving, this route is cheaper.")
        self.assertIn("If trainers offer a saving", text.split("## Keep while levelling")[0])
        self.assertEqual(text.count("If trainers offer a saving"), 1)

    def test_no_saving_line_by_default(self):
        text = self.guide(toy_plan([100]), toy.gamedata(base_recipes()))
        self.assertNotIn("Forever listing", text)

    def test_report_notes_carry_the_saving_line(self):
        from yap_forever.report import render, verdict
        gd, st = toy.gamedata(base_recipes()), toy.stock()
        p = toy_plan([100])
        line = "If trainers offer a saving, this route is cheaper."
        text = render(p, verdict(p, st), toy.market(BARS), gd, st, toy.NO_FAVOR, saving_line=line)
        self.assertEqual(text.count(line), 1)
        self.assertGreater(text.index(line), text.index("## Data notes"))
        self.assertNotIn(line, render(p, verdict(p, st), toy.market(BARS), gd, st, toy.NO_FAVOR))


class StudyHintTests(unittest.TestCase):
    """Dedicated Study hint: only the lowest profession, only rows at or above the threshold."""
    HINT = "Dedicated Study (one free point a day) would cover these"

    def guide(self, p, caps=None, skills=None, mode="gold", character=None, **kw):
        gd = toy.gamedata(base_recipes())
        st = toy.stock(skills=skills or {BS: 1, ENCH: 100})
        return render_guide(p, gd, toy.market(BARS), st, caps or {BS: 21, ENCH: 120}, character=character,
                            mode=mode, **kw)

    def two_professions(self, bs_cash, ench_cash):
        steps = [Step(BS, 1, 11, 1, "BS basic", 10, bs_cash, bs_cash * 2, {toy.COPPER_BAR: 10}),
                 Step(ENCH, 100, 110, 2, "Ench basic", 10, ench_cash, ench_cash * 2, {toy.ROD: 10})]
        return Plan(steps=steps, final_skill={BS: 11, ENCH: 110})

    def row(self, text, craft):
        (row,) = [l for l in text.splitlines() if l.startswith("- **") and f"× {craft}" in l]
        return row

    def test_hint_on_the_lowest_profession_row_at_the_threshold(self):
        p = self.two_professions(100_000, 100_000)  # 10g over 10 points: 1g a point
        text = self.guide(p, caps={BS: 11, ENCH: 110}, study_hint_gold_per_point=1)
        self.assertIn("about 1.0g a point here: " + self.HINT + " 10 points in 10 days", self.row(text, "BS basic"))
        self.assertNotIn("Dedicated Study", self.row(text, "Ench basic"))  # the other profession

    def test_no_hint_below_the_threshold(self):
        p = self.two_professions(99_999, 99_999)
        text = self.guide(p, caps={BS: 11, ENCH: 110}, study_hint_gold_per_point=1)
        self.assertNotIn(self.HINT, text)

    def test_the_default_threshold_is_100g_a_point(self):
        text = self.guide(self.two_professions(9_999_999, 0), caps={BS: 11, ENCH: 110})
        self.assertNotIn(self.HINT, text)
        text = self.guide(self.two_professions(10_000_000, 0), caps={BS: 11, ENCH: 110})
        self.assertIn("about 100g a point here", self.row(text, "BS basic"))

    def test_the_threshold_comes_from_the_setting(self):
        p = self.two_professions(100_000, 0)
        for threshold, shown in ((0.5, True), (1, True), (1.5, False)):
            with self.subTest(threshold=threshold):
                text = self.guide(p, caps={BS: 11, ENCH: 110}, study_hint_gold_per_point=threshold)
                self.assertEqual(self.HINT in text, shown)

    def test_not_taken_wording_without_the_talent(self):
        p = self.two_professions(100_000, 0)
        for character in (None, profile.Character("Alt"), profile.Character("Alt", dedicated_study=False)):
            with self.subTest(character=character):
                row = self.row(self.guide(p, caps={BS: 11, ENCH: 110}, character=character,
                                          study_hint_gold_per_point=1), "BS basic")
                self.assertTrue(row.endswith("(a legacy talent you haven't taken)"), row)

    def test_no_not_taken_wording_with_the_talent(self):
        p = self.two_professions(100_000, 0)
        row = self.row(self.guide(p, caps={BS: 11, ENCH: 110}, character=profile.Character("Alt", dedicated_study=True),
                                  study_hint_gold_per_point=1), "BS basic")
        self.assertIn(self.HINT, row)
        self.assertNotIn("haven't taken", row)

    def test_the_value_route_uses_the_net_cost(self):
        p = self.two_professions(100_000, 0)  # net cost is twice the cash: 2g a point
        text = self.guide(p, caps={BS: 11, ENCH: 110}, mode="value", study_hint_gold_per_point=2)
        self.assertIn("about 2.0g a point here", self.row(text, "BS basic"))
        text = self.guide(p, caps={BS: 11, ENCH: 110}, mode="gold", study_hint_gold_per_point=2)
        self.assertNotIn(self.HINT, text)

    def test_the_lowest_profession_is_the_one_at_the_lower_skill(self):
        p = self.two_professions(100_000, 100_000)
        text = self.guide(p, caps={BS: 11, ENCH: 110}, skills={BS: 150, ENCH: 100}, study_hint_gold_per_point=1)
        self.assertNotIn("Dedicated Study", self.row(text, "BS basic"))
        self.assertIn(self.HINT, self.row(text, "Ench basic"))

    def test_a_row_of_several_steps_is_priced_as_one(self):
        steps = [Step(BS, 1, 11, 1, "BS basic", 10, 100_000, 100_000, {toy.COPPER_BAR: 10}),
                 Step(BS, 11, 21, 1, "BS basic", 10, 300_000, 300_000, {toy.COPPER_BAR: 10})]
        p = Plan(steps=steps, final_skill={BS: 21})
        text = self.guide(p, caps={BS: 21}, skills={BS: 1}, study_hint_gold_per_point=2)
        self.assertIn("about 2.0g a point here: " + self.HINT + " 20 points in 20 days", self.row(text, "BS basic"))

    def test_one_point_row_reads_in_the_singular(self):
        p = Plan(steps=[Step(BS, 1, 2, 1, "BS basic", 1, 100_000, 100_000, {toy.COPPER_BAR: 1})], final_skill={BS: 2})
        text = self.guide(p, caps={BS: 2}, skills={BS: 1}, study_hint_gold_per_point=1)
        self.assertIn("would cover this point in 1 day", self.row(text, "BS basic"))

    def test_the_hint_does_not_replace_the_talent_line(self):
        p = self.two_professions(100_000, 0)
        text = self.guide(p, caps={BS: 11, ENCH: 110}, character=profile.Character("Alt", dedicated_study=True),
                          study_hint_gold_per_point=1)
        self.assertIn("Dedicated Study: one free point a day goes to your lowest profession", text)


class StudyHintSettingTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profile.toml"
            p.write_text('faction = "alliance"\n' + text, encoding="utf-8")
            return profile.load_profile(p)

    def test_default_is_100(self):
        self.assertEqual(self.load("").study_hint_gold_per_point, 100)
        self.assertEqual(profile.Profile().study_hint_gold_per_point, 100)

    def test_a_custom_value(self):
        self.assertEqual(self.load("study_hint_gold_per_point = 5\n").study_hint_gold_per_point, 5)
        self.assertEqual(self.load("study_hint_gold_per_point = 2.5\n").study_hint_gold_per_point, 2.5)

    def test_refused_values(self):
        for bad in ("0", "-1", "-0.5", '"100"', "true", "nan", "inf", "[5]"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as cm:
                    self.load(f"study_hint_gold_per_point = {bad}\n")
                self.assertIn("study_hint_gold_per_point", str(cm.exception))
                self.assertIn("profile.toml", str(cm.exception))


class WriteReportsTests(unittest.TestCase):
    """End to end on the fixture game data: the plan is made on the safe data, once."""

    def setUp(self):
        import shutil

        from yap_forever import cli, settings
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init"], self.paths)
        shutil.copytree(FIX, self.paths.gamedata)
        self.paths.prices.write_text(
            '{"snapshot_time": "t", "listings": {"2835": [[20, 500]], "2840": [[10, 500]]}}', encoding="utf-8")
        self.stock = self.paths.character("Alt") / "stock.toml"
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 20\n[items]\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def reports(self, **kw):
        from yap_forever import plan as plan_mod
        _table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", {BS: Goal(skill=60)}, **kw)
        return {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def test_the_belt_is_learned_at_its_inferred_skill_with_a_note(self):
        texts = self.reports()
        learn = [l for t in (texts["guide-gold"], texts["guide-value"]) for l in t.splitlines()
                 if "Learn Copper Chain Belt" in l]
        self.assertEqual(len(learn), 2)  # one learn row in each guide
        for row in learn:
            self.assertRegex(row, r"At (3[5-9]|[4-9]\d):")  # never before the inferred 35
            self.assertIn("listed from 30 in the Forever data", row)

    def test_a_recipe_goal_is_planned_to_the_inferred_skill(self):
        from yap_forever import plan as plan_mod
        plan_mod.write_reports(self.paths, self.stock, "Neutral", {BS: Goal(recipe="Copper Chain Belt")})
        text = next(self.paths.reports.glob("*-guide-gold.md")).read_text(encoding="utf-8")
        self.assertIn("to 35", text.splitlines()[0])

    def test_the_header_line_goes_to_the_route_it_is_for(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        with mock.patch.object(plan_mod, "listed_savings", return_value={"gold": 1_234_500}):
            texts = self.reports()
        line = plan_mod.saving_line(1_234_500)
        for key in ("guide-gold", "plan-gold"):
            self.assertEqual(texts[key].count(line), 1, key)
        for key in ("guide-value", "plan-value"):
            self.assertNotIn("Forever listing", texts[key])

    def test_no_header_line_when_the_data_has_no_inferred_recipe(self):
        trainer = self.paths.gamedata / "Trainer.lua"
        text = trainer.read_text(encoding="utf-8")
        trainer.write_text(text.split("ns.TrainerInferred")[0], encoding="utf-8")
        for text in self.reports().values():
            self.assertNotIn("Forever listing", text)

    def test_the_hint_threshold_reaches_the_guide(self):
        self.assertNotIn("Dedicated Study (one free", self.reports()["guide-gold"])
        texts = self.reports(study_hint_gold_per_point=0.0001)
        self.assertIn("Dedicated Study (one free point a day) would cover these", texts["guide-gold"])


if __name__ == "__main__":
    unittest.main()
