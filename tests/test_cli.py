import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from yap_forever import cli, settings
from yap_forever.__main__ import python_too_old


def run(argv, paths):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv, paths)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")

    def tearDown(self):
        self._tmp.cleanup()

    def test_python_too_old_message(self):
        self.assertEqual(python_too_old((3, 10)), "yap-forever needs Python 3.11 or newer; you have 3.10.")
        self.assertIsNone(python_too_old((3, 11)))

    def test_main_module_defines_on_old_python(self):
        # Python < 3.10 evaluates annotations like "str | None" when a function is defined, which
        # would crash before the version message. Only a lazily-evaluated module is safe there.
        import ast
        src = (Path(cli.__file__).parent / "__main__.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                   and any(a.name == "annotations" for a in n.names) for n in tree.body)
        unions = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)]
        self.assertTrue(lazy or not unions)

    def test_init_prints_cyrillic_home_on_ansi_console(self):
        # Windows pipes stdout in the ANSI code page; Claude Code reads it through a pipe.
        import subprocess
        import sys
        home = Path(self._tmp.name) / "Мой дом"
        env = dict(os.environ, YAP_FOREVER_HOME=str(home), PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, "-m", "yap_forever", "init"], env=env,
                           cwd=Path(cli.__file__).parent.parent, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-300:])
        self.assertTrue((home / "profile.toml").exists())

    def test_command_hint_windows(self):
        self.assertEqual(cli.command_hint("check", "nt"), "py -3 -m yap_forever check")
        self.assertEqual(cli.command_hint("check", "posix"), "python3 -m yap_forever check")

    def test_init_creates_files_and_keeps_existing(self):
        code, _ = run(["init"], self.paths)
        self.assertEqual(code, 0)
        for p in (self.paths.profile, self.paths.credentials, self.paths.cache, self.paths.reports):
            self.assertTrue(p.exists(), p)
        self.paths.profile.write_text('region = "us"\nfaction = "horde"\n', encoding="utf-8")
        run(["init"], self.paths)
        self.assertEqual(self.paths.profile.read_text(encoding="utf-8"), 'region = "us"\nfaction = "horde"\n')

    @unittest.skipIf(os.name == "nt", "file modes are POSIX only")
    def test_init_credentials_mode_600(self):
        run(["init"], self.paths)
        self.assertEqual(self.paths.credentials.stat().st_mode & 0o777, 0o600)

    def test_check_reports_missing_credentials(self):
        run(["init"], self.paths)
        code, out = run(["check", "--offline"], self.paths)
        self.assertEqual(code, 1)
        line = next(l for l in out.splitlines() if l.startswith("credentials"))
        self.assertIn("MISSING:", line)
        self.assertIn(str(self.paths.credentials), line)
        self.assertIn("develop.battle.net", line)

    def test_prices_without_house_names_probe(self):
        run(["init"], self.paths)
        code, out = run(["prices"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("probe"), out)

    def test_plan_without_prices_names_next_step(self):
        run(["init"], self.paths)
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("prices"), out)

    def test_plan_offline_game_data_names_network(self):
        import urllib.error
        from unittest import mock
        run(["init"], self.paths)
        self.paths.prices.write_text('{"snapshot_time": "t", "listings": {}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("network", out)

    def test_plan_refuses_prices_from_another_house(self):
        from yap_forever import profile
        run(["init"], self.paths)
        profile.save_house(self.paths.house, 11, "eu", 2)
        self.paths.prices.write_text('{"snapshot_time": "t", "house": 10, "region": "eu", "ruleset": 2, '
                                     '"listings": {}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("prices"), out)
        self.assertIn("house 10", out)

    def ready_home(self):
        import shutil
        run(["init"], self.paths)
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        self.paths.prices.write_text('{"snapshot_time": "t", "listings": {"2835": [[20, 500]]}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        return stock

    def test_plan_writes_both_routes(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn("Least gold", out)
        self.assertIn("Least total value", out)
        for name in ("guide-gold", "guide-value", "plan-gold", "plan-value"):
            self.assertTrue(list(self.paths.reports.glob(f"*-{name}.md")), name)

    def add_character(self, name, stock_text="level = 20\n[items]\n"):
        text = self.paths.profile.read_text(encoding="utf-8")
        self.paths.profile.write_text(text + f'\n[characters."{name}"]\nfavor_standing = "Neutral"\n',
                                      encoding="utf-8")
        stock = self.paths.character(name) / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text(stock_text, encoding="utf-8")

    def report_names(self):
        return sorted(f.name for f in self.paths.reports.glob("*.md"))

    def test_plan_refuses_a_character_on_another_ruleset_or_faction(self):
        self.ready_home()
        for line, where in (("ruleset = 3\n", "ruleset 3"), ('faction = "horde"\n', "horde")):
            with self.subTest(line=line):
                text = self.paths.profile.read_text(encoding="utf-8")
                self.paths.profile.write_text(text + line, encoding="utf-8")
                code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"],
                                self.paths)
                self.assertEqual(code, 1)
                self.assertIn("no prices yet", out)
                self.assertIn("isn't supported yet", out)
                self.assertIn(where, out)
                self.assertEqual(self.report_names(), [])
                self.paths.profile.write_text(text, encoding="utf-8")

    def test_plan_for_the_profiles_own_group_is_not_refused(self):
        self.ready_home()
        text = self.paths.profile.read_text(encoding="utf-8")
        self.paths.profile.write_text(text + 'ruleset = 2\nfaction = "alliance"\n', encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)

    def test_plan_reports_carry_the_characters_name(self):
        from datetime import date
        self.ready_home()
        run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        today = date.today().isoformat()
        self.assertEqual(self.report_names(), sorted(
            f"{today}-firstname-lastname-{kind}-{mode}.md" for kind in ("guide", "plan")
            for mode in ("gold", "value")))

    def test_plan_for_two_characters_keeps_both_sets_of_reports(self):
        self.ready_home()
        self.add_character("Testy Example")
        for name in ("Firstname Lastname", "Testy Example"):
            code, out = run(["plan", "--character", name, "--prof", "blacksmithing:20"], self.paths)
            self.assertEqual(code, 0, out)
        names = self.report_names()
        self.assertEqual(len(names), 8)
        self.assertEqual(sum("testy-example" in n for n in names), 4)

    def test_plan_for_names_that_clash_gives_each_its_own_hash(self):
        import hashlib
        self.ready_home()
        self.add_character("firstname  lastname")
        for name in ("Firstname Lastname", "firstname  lastname"):
            code, out = run(["plan", "--character", name, "--prof", "blacksmithing:20"], self.paths)
            self.assertEqual(code, 0, out)
        names = self.report_names()
        self.assertEqual(len(names), 8)
        for name in ("Firstname Lastname", "firstname  lastname"):
            h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
            self.assertEqual(sum(f"-lastname-{h}-" in n for n in names), 4, name)

    def test_write_reports_without_a_character_keeps_the_old_names(self):
        from datetime import date

        from yap_forever import plan as plan_mod
        from yap_forever.config import Goal
        stock = self.ready_home()
        plan_mod.write_reports(self.paths, stock, "Neutral", {164: Goal(skill=20)})
        today = date.today().isoformat()
        self.assertEqual(self.report_names(), sorted(
            f"{today}-{kind}-{mode}.md" for kind in ("guide", "plan") for mode in ("gold", "value")))

    def bags_only_home(self, bags_text='profs = ["blacksmithing"]\nbag_slots = 25\n[items]\n2835 = 3\n'):
        stock = self.ready_home()
        stock.unlink()
        bags = stock.parent / "bags.toml"
        bags.write_text(bags_text, encoding="utf-8")
        return stock, bags

    def test_plan_converts_a_bags_file_once_and_says_what_to_fill_in(self):
        stock, bags = self.bags_only_home()
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertTrue(stock.exists())
        self.assertTrue(bags.exists())
        lines = [l for l in out.splitlines() if str(stock) in l and "bags.toml" in l]
        self.assertEqual(len(lines), 1, out)
        for word in ("level", "[skills]", "[goals]", "gold goes under [gold] in profile.toml"):
            self.assertIn(word, lines[0])
        self.assertNotIn("cash_gold", lines[0])
        self.assertIn("name the professions to plan", out)
        again_code, again = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(again_code, 1)
        self.assertNotIn("bags.toml", again)
        self.assertIn("name the professions to plan", again)

    def test_plan_with_a_converted_bags_file_plans_with_prof_flags(self):
        stock, _ = self.bags_only_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn(str(stock), out)
        self.assertEqual(len(self.report_names()), 4)

    def test_plan_leaves_a_stock_file_alone_when_a_bags_file_sits_beside_it(self):
        stock, bags = self.bags_only_home()
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertNotIn("bags.toml", out)
        self.assertEqual(stock.read_text(encoding="utf-8"), "level = 20\n[items]\n")

    def test_plan_with_a_damaged_bags_file_names_it(self):
        stock, bags = self.bags_only_home("profs = [")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(str(bags), out)
        self.assertFalse(stock.exists())

    def test_plan_with_neither_file_still_asks_for_a_stock_file(self):
        stock, bags = self.bags_only_home()
        bags.unlink()
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("no stock file for Firstname Lastname", out)

    def guide_text(self):
        (path,) = self.paths.reports.glob("*-guide-gold.md")
        return path.read_text(encoding="utf-8")

    def test_plan_with_damaged_trainer_file_still_renders_and_says_why(self):
        self.ready_home()
        (self.paths.gamedata / "foreverNpcDB.lua").write_text("QuestieDB.npcData = [[return {", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertNotIn("Traceback", out)
        text = self.guide_text()
        self.assertEqual(text.count("Trainer names are left out"), 1)
        self.assertIn("foreverNpcDB.lua is damaged", text)

    def test_plan_with_a_damaged_game_data_file_names_it_without_a_traceback(self):
        self.ready_home()
        bad = self.paths.gamedata / "Vendor.lua"
        bad.write_text("<html>\n<body>Bad gateway</body>\n</html>\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertIn(str(bad), out)
        self.assertIn("delete it", out)

    def test_plan_with_an_error_page_as_a_download_saves_nothing_and_says_so(self):
        import shutil
        from unittest import mock

        from tests.test_gamedata import HTML_LINES, _serve
        self.ready_home()
        shutil.rmtree(self.paths.gamedata)  # an empty cache: everything is downloaded
        with mock.patch("urllib.request.urlopen", side_effect=_serve({"ItemSparse.csv": HTML_LINES})):
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertIn("ItemSparse.csv is not game data", out)
        self.assertFalse((self.paths.gamedata / "ItemSparse.csv").exists())
        self.assertEqual(list(self.paths.reports.glob("*.md")) if self.paths.reports.exists() else [], [])

    def test_plan_offline_with_trainer_files_missing_still_renders(self):
        import urllib.error
        from unittest import mock
        self.ready_home()
        for name in ("foreverNpcDB.lua", "foreverObjectDB.lua", "AreaTable.csv"):
            (self.paths.gamedata / name).unlink()
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn("Trainer names are left out", self.guide_text())

    def test_plan_passes_the_profile_faction_to_the_guide(self):
        from unittest import mock
        self.ready_home()
        with mock.patch("yap_forever.plan.render_guide", return_value="guide") as guide:
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertEqual(guide.call_args.kwargs["trainer_info"].faction, "alliance")

    def test_plan_passes_the_characters_talents_and_reading(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        self.ready_home()
        text = self.paths.profile.read_text(encoding="utf-8")
        self.paths.profile.write_text(
            'working_overtime_reading = "points"\n' + text + 'working_overtime = 3\n', encoding="utf-8")
        with mock.patch.object(plan_mod, "write_reports", return_value=("table", {})) as w:
            code, _ = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0)
        args = w.call_args.args
        self.assertEqual(args[4].working_overtime, 3)
        self.assertEqual(args[5], "points")

    def test_plan_passes_the_profile_study_hint_threshold(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        self.ready_home()
        with mock.patch.object(plan_mod, "write_reports", return_value=("table", {})) as w:
            run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
            self.assertEqual(w.call_args.kwargs["study_hint_gold_per_point"], 100)
            text = self.paths.profile.read_text(encoding="utf-8")
            self.paths.profile.write_text("study_hint_gold_per_point = 7.5\n" + text, encoding="utf-8")
            run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
            self.assertEqual(w.call_args.kwargs["study_hint_gold_per_point"], 7.5)

    def test_plan_overtime_rank_zero_leaves_the_guide_unchanged(self):
        self.ready_home()
        run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        before = {f.name: f.read_text(encoding="utf-8") for f in self.paths.reports.glob("*.md")}
        text = self.paths.profile.read_text(encoding="utf-8")
        self.paths.profile.write_text(
            'working_overtime_reading = "points"\n' + text + 'working_overtime = 0\n', encoding="utf-8")
        run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        after = {f.name: f.read_text(encoding="utf-8") for f in self.paths.reports.glob("*.md")}
        self.assertEqual(before, after)
        self.assertEqual(len(after), 4)

    def test_plan_uses_saved_goals(self):
        stock = self.ready_home()
        stock.write_text("level = 20\n[items]\n\n[goals]\nblacksmithing = 20\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 0, out)

    def test_plan_without_goals_names_flag(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("--prof blacksmithing:225", out)

    def test_plan_bad_recipe_target_names_it(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:Golden Nothing"],
                        self.paths)
        self.assertEqual(code, 1)
        self.assertIn("no Blacksmithing recipe called 'Golden Nothing'", out)

    def test_plan_bad_prof_flag(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "cooking:150"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("unknown profession", out)

    def test_plan_rejects_three_professions_or_a_repeat(self):
        self.ready_home()
        for flags in (["blacksmithing:20", "enchanting:20", "tailoring:20"], ["blacksmithing:20", "blacksmithing:30"]):
            argv = ["plan", "--character", "Firstname Lastname"] + [x for f in flags for x in ("--prof", f)]
            code, out = run(argv, self.paths)
            self.assertEqual(code, 1, flags)
            self.assertIn("one or two different professions", out)

    def test_plan_numeric_profession_must_be_known(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "129:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("unknown profession", out)

    def test_plan_rejects_three_saved_goals(self):
        self.ready_home()
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.write_text("level = 20\n[items]\n\n[goals]\nblacksmithing = 20\nenchanting = 20\ntailoring = 20\n",
                         encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("plan one or two at a time", out)

    def test_plan_unknown_character_lists_known(self):
        run(["init"], self.paths)
        code, out = run(["plan", "--character", "Bob"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("Firstname Lastname", out)

    def test_cli_budget_flag_wins(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Budget
        stock = self.ready_home()
        stock.write_text('level = 20\n[items]\n\n[goals]\nbudget = 9\nbudget_order = ["enchanting", "blacksmithing"]\n'
                         'blacksmithing = 20\nenchanting = 20\n', encoding="utf-8")
        me = ["plan", "--character", "Firstname Lastname"]
        with mock.patch.object(plan_mod, "write_reports", return_value=("table", {})) as w:
            for argv, want in (([], Budget(9, (333, 164))),
                               (["--budget", "4.5"], Budget(4.5, (333, 164))),
                               (["--budget", "4.5", "--order", "even"], Budget(4.5, None)),
                               (["--order", "Blacksmithing,enchanting"], Budget(9, (164, 333))),
                               (["--order", "enchanting"], Budget(9, (333, 164)))):
                code, out = run(me + argv, self.paths)
                self.assertEqual(code, 0, out)
                self.assertEqual(w.call_args.kwargs["target"], want, argv)
            # one profession: the order is ignored
            code, out = run(me + ["--prof", "blacksmithing:20", "--budget", "3"], self.paths)
            self.assertEqual((code, w.call_args.kwargs["target"]), (0, Budget(3, None)), out)
            stock.write_text("level = 20\n[items]\n\n[goals]\nblacksmithing = 20\n", encoding="utf-8")
            code, out = run(me, self.paths)
            self.assertEqual((code, w.call_args.kwargs["target"]), (0, None), out)
        for bad, said in ((["--budget", "-1"], "--budget"), (["--budget", "lots"], "--budget"),
                          (["--order", "even"], "--order goes with a budget")):
            code, out = run(me + bad, self.paths)
            self.assertEqual(code, 1, bad)
            self.assertIn(said, out)

    def test_order_name_not_planned_is_refused(self):
        stock = self.ready_home()
        stock.write_text("level = 20\n[items]\n\n[goals]\nbudget = 9\nblacksmithing = 20\nenchanting = 20\n",
                         encoding="utf-8")
        for order, said in (("tailoring,blacksmithing", "Tailoring, which is not planned"), ("cooking", "unknown profession"),
                            ("enchanting,enchanting", "twice")):
            code, out = run(["plan", "--character", "Firstname Lastname", "--order", order], self.paths)
            self.assertEqual(code, 1, order)
            self.assertIn(said, out)
        stock.write_text('level = 20\n[items]\n\n[goals]\nbudget = 9\nbudget_order = ["tailoring"]\n'
                         "blacksmithing = 20\nenchanting = 20\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("Tailoring", out)
        self.assertIn("not planned", out)

    def test_plan_with_a_budget_cuts_both_routes(self):
        self.ready_home()
        me = ["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"]
        code, out = run(me + ["--budget", "0"], self.paths)
        self.assertEqual(code, 0, out)
        for m in ("gold", "value"):
            guide = next(self.paths.reports.glob(f"*-guide-{m}.md")).read_text(encoding="utf-8")
            report = next(self.paths.reports.glob(f"*-plan-{m}.md")).read_text(encoding="utf-8")
            for text in (guide, report):
                self.assertIn("0g doesn't reach the first stop: nothing is planned yet.", text)
                self.assertIn("The next stop, Blacksmithing 20, costs about", text)
            self.assertIn("planned to your 0g budget", report)
        code, out = run(me + ["--budget", "1000"], self.paths)
        self.assertEqual(code, 0, out)
        guide = next(self.paths.reports.glob("*-guide-gold.md")).read_text(encoding="utf-8")
        self.assertIn("1000g takes Blacksmithing to 20 (", guide)
        self.assertNotIn("The next stop", guide)

    def test_plan_with_a_budget_and_two_professions(self):
        self.ready_home()  # the fixture has no Enchanting recipe usable at 1: it can't advance
        me = ["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20", "--prof", "enchanting:20"]
        code, out = run(me + ["--budget", "1000", "--order", "enchanting,blacksmithing"], self.paths)
        self.assertEqual(code, 0, out)
        for m in ("gold", "value"):
            guide = next(self.paths.reports.glob(f"*-guide-{m}.md")).read_text(encoding="utf-8")
            report = next(self.paths.reports.glob(f"*-plan-{m}.md")).read_text(encoding="utf-8")
            for text in (guide, report):
                self.assertIn("1000g takes Blacksmithing to 20 (", text)
                self.assertIn("Enchanting gets none of it: no usable recipe at 1.", text)
            self.assertIn("Level one profession at a time: Enchanting first, then Blacksmithing.", guide)
        code, out = run(me + ["--budget", "0"], self.paths)
        self.assertEqual(code, 0, out)
        guide = next(self.paths.reports.glob("*-guide-gold.md")).read_text(encoding="utf-8")
        self.assertIn("0g doesn't reach the first stop: nothing is planned yet.", guide)
        self.assertIn("The next stop, Blacksmithing 20, costs about", guide)
        self.assertNotIn("The next stop, Enchanting", guide)
        self.assertIn("Level both professions side by side", guide)

    def test_plan_with_a_budget_and_a_recipe_target_plans_the_recipe_in_full(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:2660",
                         "--budget", "0"], self.paths)
        self.assertEqual(code, 0, out)
        guide = next(self.paths.reports.glob("*-guide-gold.md")).read_text(encoding="utf-8")
        report = next(self.paths.reports.glob("*-plan-gold.md")).read_text(encoding="utf-8")
        self.assertNotIn("doesn't reach", guide + report)
        self.assertNotIn("planned to your", report)
        self.assertIn("once", guide)
        line = "The 0g budget is not applied: a recipe target is planned in full."
        self.assertIn(line, out)  # said in the plan output, the guide header and the report verdict
        verdict = report[report.index("## Verdict"):].split("\n## ")[0]
        self.assertIn(line, verdict)
        self.assertIn(line, guide[:guide.index("## ")])
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:2660"], self.paths)
        guide = next(self.paths.reports.glob("*-guide-gold.md")).read_text(encoding="utf-8")
        self.assertNotIn("budget is not applied", out + guide)  # no budget, nothing to say

    def test_a_budget_next_to_a_recipe_goal_says_it_is_not_applied(self):
        # the other profession's skill target is not cut either; the saved [goals] budget is the likely case
        stock = self.ready_home()
        stock.write_text('level = 20\n[items]\n\n[goals]\nbudget = 12.5\nblacksmithing = "2660"\nenchanting = 20\n',
                         encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 0, out)
        line = "The 12.5g budget is not applied: a recipe target is planned in full."
        self.assertEqual(out.count(line), 1, out)
        for m in ("gold", "value"):
            guide = next(self.paths.reports.glob(f"*-guide-{m}.md")).read_text(encoding="utf-8")
            report = next(self.paths.reports.glob(f"*-plan-{m}.md")).read_text(encoding="utf-8")
            self.assertEqual(guide.count(line), 1, m)
            self.assertEqual(report.count(line), 1, m)
            self.assertNotIn("planned to your", report)
            self.assertNotIn(" takes ", guide)
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20",
                         "--prof", "enchanting:20"], self.paths)  # skill targets only: the budget is applied
        self.assertEqual(code, 0, out)
        self.assertNotIn("not applied", out)


    def test_plan_passes_the_characters_own_faction(self):
        # C20: the faction write_reports names trainers and capitals for is the character's own, else the profile's.
        # The group check refuses a character on another faction's prices today, so it is bypassed here.
        from unittest import mock

        from yap_forever import plan as plan_mod, profile
        self.ready_home()
        with mock.patch.object(plan_mod, "write_reports", return_value=("table", {})) as w:
            run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
            self.assertEqual(w.call_args.kwargs["faction"], "alliance")
            text = self.paths.profile.read_text(encoding="utf-8")
            self.paths.profile.write_text(text + 'faction = "horde"\ncapital = "undercity"\n', encoding="utf-8")
            with mock.patch.object(profile.Profile, "group_of", return_value=(2, "alliance")):
                code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"],
                                self.paths)
            self.assertEqual(code, 0, out)
            self.assertEqual(w.call_args.kwargs["faction"], "horde")
            self.assertEqual(w.call_args.args[4].capital, "undercity")

class FreeSkipReportTests(unittest.TestCase):
    """#90 through write_reports: a trip whose route-without costs the same is planned without and said, before the
    mailbox trips, the listed saving, the table and the skip clauses shown."""
    LINE = ("Planned without the trip back to the Master Blacksmith at 240 for BS late 1: the route without it costs "
            "the same.")

    def setUp(self):
        import json
        import shutil

        from tests.test_trips import free_toy
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init"], self.paths)
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        self.inputs = free_toy()
        listings = {str(i): [[100, 100000]] for i in (2840, 3575)}  # Copper Bar and Iron Bar at 1s
        self.paths.prices.write_text(json.dumps({"snapshot_time": "t", "listings": listings}), encoding="utf-8")
        self.stock = self.paths.character("Alt") / "stock.toml"
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 60\n[items]\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def reports(self, **kw):
        from unittest import mock

        from yap_forever import gamedata, plan as plan_mod
        from yap_forever.config import Goal
        with mock.patch.object(gamedata, "load_gamedata", return_value=self.inputs.gd):
            table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", {164: Goal(skill=300)}, **kw)
        return table, {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def test_free_skip_adopted_and_said(self):
        _table, texts = self.reports()
        for m in ("gold", "value"):
            guide, report = texts[f"guide-{m}"], texts[f"plan-{m}"]
            self.assertNotIn("**Trip:** back to", guide)  # no trip back at 240
            self.assertNotIn("start crafting BS late 1", guide)
            self.assertIn("Blacksmithing rank to 300", guide)
            self.assertEqual(guide.count(self.LINE), 1, m)
            self.assertIn(self.LINE, guide[:guide.index("## ")])
            self.assertNotIn("no extra cost", guide)
            notes = report[report.index("## Data notes"):]
            self.assertIn(f"- {self.LINE}", notes)

    def test_table_uses_adopted_route(self):
        table, _texts = self.reports()
        self.assertIn("| Trips away | 2 | 2 |", table)  # the two rank trips, not the trip back at 240
        self.assertIn("both guides are the same route", table)  # adopted once for both: still one route

    def test_shown_skips_measure_against_the_adopted_route(self):
        from unittest import mock

        from yap_forever import plan as plan_mod
        with mock.patch.object(plan_mod, "take_free_skips", wraps=plan_mod.take_free_skips) as take, \
                mock.patch.object(plan_mod, "trip_alternatives", wraps=plan_mod.trip_alternatives) as alts:
            self.reports()
        self.assertEqual(take.call_count, 1)  # gold and value are one route: adopted once
        self.assertIsNone(take.call_args.kwargs["fits"])  # no budget
        self.assertEqual(take.call_args.kwargs["also"], ("value",))  # free in both measures
        self.assertEqual([c.kwargs["excluded"] for c in alts.call_args_list], [frozenset({1})])

    def test_free_skip_under_a_budget(self):
        import re
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Budget
        from yap_forever.planner import Plan
        with mock.patch.object(plan_mod, "take_free_skips", wraps=plan_mod.take_free_skips) as take:
            _table, texts = self.reports(target=Budget(1000))
        guide = texts["guide-gold"]
        self.assertIn(self.LINE, guide)
        spent = re.search(r"1000g takes Blacksmithing to 300 \((.+?)\)\.", guide).group(1)
        self.assertIn(f"**Gold to bring: {spent}**", guide)  # the budget line is the adopted route's gold to bring
        fits = take.call_args.kwargs["fits"]
        self.assertTrue(fits(Plan()))
        self.assertFalse(fits(Plan(fees=10_000_001)))  # a fee over 1000g doesn't fit

    def test_distinct_routes_are_skipped_on_their_own(self):
        # gold and value on two routes to the same caps: each gets its own free skips, not the gold route's
        from types import SimpleNamespace
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.planner import Plan
        gold, value = Plan(cash_total=1), Plan(cash_total=2)
        same_caps = SimpleNamespace(caps={164: 300})
        with mock.patch.object(plan_mod, "take_free_skips", side_effect=lambda r, *_a, **_k: (r, [])) as take:
            out = plan_mod._free_skips({"gold": gold, "value": value}, {"gold": same_caps, "value": same_caps}, {},
                                       "as_needed", None, None)
        self.assertIs(out["gold"][0], gold)
        self.assertIs(out["value"][0], value)
        self.assertEqual([c.kwargs["also"] for c in take.call_args_list], [(), ()])  # not one route: one measure each
        with mock.patch.object(plan_mod, "take_free_skips", side_effect=lambda r, *_a, **_k: (r, [])) as take:
            out = plan_mod._free_skips({"gold": gold, "value": gold}, {"gold": same_caps, "value": same_caps}, {},
                                       "as_needed", None, None)
        self.assertIs(out["value"], out["gold"])
        self.assertEqual([c.kwargs["also"] for c in take.call_args_list], [("value",)])

    def test_free_skip_over_the_budget_is_kept(self):
        # a real route-without that costs the same gold out of pocket but more gold to bring: at 225 the bank's 300
        # Copper Bars cover the yellow copper crafts to 300 but not their buffer, which the shopping list buys, while
        # the trip back's orange iron recipe uses the bank's 60 Iron Bars. Kept under a budget the route fits exactly.
        import dataclasses
        from types import SimpleNamespace
        from unittest import mock

        from tests import toy
        from yap_forever import plan as plan_mod
        from yap_forever.config import Budget
        from yap_forever.gamedata import Rank
        gd = toy.gamedata([toy.recipe(1, "BS late 1", 164, {3575: 1}, t=(240, 300, 300, 300), req=240),
                           toy.recipe(9, "BS bar", 164, {2840: 1}, t=(1, 240, 300, 300))])
        gd.trainer_ranks[164] = gd.trainer_ranks[164] + [Rank(300, 50000, 200, 35)]
        self.inputs = SimpleNamespace(gd=gd)
        self.stock.write_text("level = 60\n[items]\n2840 = 300\n3575 = 60\n\n[skills]\nblacksmithing = 225\n",
                              encoding="utf-8")
        real = plan_mod.settle_routes

        def apart(candidates, caps):  # the value route its own plan, so only the gold measure decides
            routes, _same = real(candidates, caps)
            return {"gold": routes["gold"], "value": dataclasses.replace(routes["value"])}, False
        with mock.patch.object(plan_mod, "settle_routes", side_effect=apart):
            _table, free = self.reports()
            _table, cut = self.reports(target=Budget(5))
        line = "Planned without the trip back to the Master Blacksmith at 240 for BS late 1"
        self.assertIn(line, free["guide-gold"])  # no budget: the same gold out of pocket, one trip less
        self.assertIn("**Gold to bring: 5.4g**", free["guide-gold"])
        guide = cut["guide-gold"]
        self.assertIn("5g takes Blacksmithing to 300 (5.0g).", guide)
        self.assertNotIn(line, guide)
        self.assertIn("at 240 for BS late 1.", guide)  # the trip back stays


class CouldAlsoMakeWiringTests(unittest.TestCase):
    """#95 through write_reports: a Merchant's Favor recipe the character could make is suggested in both guides and
    reports, its materials from the group's mail and priced against the group's gold ([gold], not cash_gold); a Favor
    goal is planned, not suggested."""
    ROW = ("- **Plate of Ana** (Blacksmithing 25, for level 20): 30 of your 40 Favor; materials about 2s on the AH, "
           "1 Iron Bar (mail from Bram Ironhide).")

    def setUp(self):
        import json
        import shutil

        from tests import toy
        from yap_forever.gamedata import ItemInfo
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init"], self.paths)
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        self.gd = toy.gamedata([toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
                                toy.recipe(7, "Plate of Ana", 164, {toy.IRON_BAR: 3}, (9001, 1), source="scroll",
                                           scroll=toy.SCROLL)])
        self.gd.items[9001] = ItemInfo(9001, "Plate of Ana", 2, 25, 4, 100, 400, bonding=2, required_level=20)
        listings = {str(i): [[100, 100000]] for i in (toy.COPPER_BAR, toy.IRON_BAR)}  # 1s each
        self.paths.prices.write_text(json.dumps({"snapshot_time": "t", "listings": listings}), encoding="utf-8")
        self.stock = self.paths.character("Ana Brightforge") / "stock.toml"
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 22\nfavor = 40\ncash_gold = 5\n[skills]\nblacksmithing = 30\n[items]\n",
                              encoding="utf-8")
        self.bram = toy.stock({toy.IRON_BAR: 1})

    def tearDown(self):
        self._tmp.cleanup()

    def reports(self, goal=None, gold=1.0, alone=False, favor=None):
        from unittest import mock

        from yap_forever import gamedata, plan as plan_mod
        from yap_forever.config import Goal
        from yap_forever.favor import FavorData
        from yap_forever.shared import Group
        group = None if alone else Group(2, "alliance", gold, {"Bram Ironhide": self.bram})
        with mock.patch.object(gamedata, "load_gamedata", return_value=self.gd), \
                mock.patch.object(plan_mod, "load_favor", return_value=favor or FavorData({7: 30}, {7: 25}, [])):
            _table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", {164: goal or Goal(skill=40)},
                                                   group=group)
        return {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def test_suggested_in_both_guides_and_reports(self):
        texts = self.reports()
        for m in ("gold", "value"):
            guide, report = texts[f"guide-{m}"], texts[f"plan-{m}"]
            self.assertIn("## You could also make\n", guide)
            self.assertIn(self.ROW, guide)
            favor = report[report.index("## Merchant's Favor"):report.index("## Totals")]
            self.assertIn("**You could also make**", favor)
            self.assertIn(self.ROW, favor)
            self.assertIn("- Merchant's Favor recipes are not used to level (see You could also make).", report)
            self.assertIn("Spent 0 of 40 Favor.", report)

    def test_the_groups_gold_not_cash_gold(self):
        # 2s to buy; cash_gold is 5g but the group's [gold] is 1s: not suggested
        texts = self.reports(gold=0.01)
        self.assertNotIn("You could also make", texts["guide-gold"])
        self.assertNotIn("Plate of Ana", texts["plan-gold"])
        alone = self.reports(alone=True)["guide-gold"]  # no group: the stock's own cash_gold, and no mail
        self.assertIn("- **Plate of Ana** (Blacksmithing 25, for level 20): 30 of your 40 Favor; materials about 3s "
                      "on the AH.", alone)

    def test_goal_planned_not_suggested(self):
        from yap_forever.config import Goal
        texts = self.reports(goal=Goal(recipe="Plate of Ana"))
        self.assertNotIn("You could also make", texts["guide-gold"])
        self.assertIn("Spent 30 of 40 Favor.", texts["plan-gold"])

    def test_level_not_set_says_so(self):
        # a stock file without `level`: no item is suggested, and the guide's notes and the report's data notes say why
        line = "- Set level in stock.toml to get Merchant's Favor item suggestions."
        with_level = self.reports()
        self.assertNotIn(line, with_level["guide-gold"] + with_level["plan-gold"])
        self.stock.write_text("favor = 40\ncash_gold = 5\n[skills]\nblacksmithing = 30\n[items]\n", encoding="utf-8")
        texts = self.reports()
        for m in ("gold", "value"):
            guide, report = texts[f"guide-{m}"], texts[f"plan-{m}"]
            self.assertNotIn("Plate of Ana", guide)
            self.assertIn(line, guide[guide.index("## Notes"):])
            self.assertIn(line, report[report.index("## Data notes"):])

    def test_guide_cut_report_complete(self):
        # the guide lists at most favor_suggest.GUIDE_LIMIT of each kind (1 here), the report every suggestion
        from unittest import mock

        from tests import toy
        from yap_forever import favor_suggest
        from yap_forever.favor import FavorData
        from yap_forever.gamedata import ItemInfo
        self.gd.recipes[8] = toy.recipe(8, "Helm of Ana", 164, {toy.IRON_BAR: 3}, (9002, 1), source="scroll",
                                        scroll=toy.SCROLL)
        self.gd.items[9002] = ItemInfo(9002, "Helm of Ana", 2, 25, 4, 100, 400, bonding=2, required_level=22)
        with mock.patch.object(favor_suggest, "GUIDE_LIMIT", 1):
            texts = self.reports(favor=FavorData({7: 30, 8: 30}, {7: 25, 8: 25}, []))
        guide, report = texts["guide-gold"], texts["plan-gold"]
        self.assertIn("- **Helm of Ana**", guide)  # level 22, the character's: first
        self.assertNotIn("- **Plate of Ana**", guide)
        self.assertIn("\n\nand 1 more.\n", guide)
        self.assertIn("- **Helm of Ana**", report)
        self.assertIn("- **Plate of Ana**", report)
        self.assertNotIn("and 1 more.", report)


if __name__ == "__main__":
    unittest.main()
