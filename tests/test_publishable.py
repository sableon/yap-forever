"""Checks on what the public repository ships: manifests, skill, credits, no private details."""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

from yap_forever import gamedata

ROOT = Path(__file__).resolve().parent.parent  # the repository: the marketplace and the project files
PLUGIN = ROOT / "plugin"  # what players install (the marketplace's source)
SKILL = PLUGIN / "skills" / "forever-professions"


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            out[key.strip()] = value.strip()
    return out


def frontmatter_list(text: str, key: str) -> list[str]:
    """The items of a YAML block list under `key` in the frontmatter (`  - item` lines)."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    items, inside = [], False
    for line in (m.group(1) if m else "").splitlines():
        if not line.startswith(" "):
            inside = line.split(":", 1)[0].strip() == key
        elif inside and line.lstrip().startswith("- "):
            items.append(line.lstrip()[2:].strip())
    return items


def tracked_text_files() -> list[Path]:
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.split()
    files = []
    for n in names:
        p = ROOT / n
        if p.is_file() and p.suffix not in {".png", ".jpg", ".gif", ".ico"}:
            files.append(p)
    return files


# Patterns are written so they never match this file's own source.
PRIVATE = [
    ("IPv4 address", re.compile(r"(?<![\d.])(?!127\.0\.0\.1)(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")),
    ("macOS home path", re.compile(r"/Use[r]s/")),
    ("Linux home path", re.compile(r"/hom[e]/\w")),
    ("Windows home path", re.compile(r"C:\\Use[r]s\\", re.I)),
    ("email address", re.compile(r"\b(?!noreply@)[\w.+-]+@(?!users\.noreply\.)[\w-]+\.[a-z]{2,}\b", re.I)),
    ("ssh key option", re.compile(r"\bss[h] -i\b")),
]


class PublishableTests(unittest.TestCase):
    def test_manifests_valid(self):
        plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], "yap-forever")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(market["plugins"][0]["source"], "./plugin")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(plugin["license"], "GPL-3.0-or-later")

    def test_one_version_in_the_package_and_the_manifest(self):
        import yap_forever
        plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], yap_forever.__version__)

    def test_the_manifest_version_is_not_behind_the_newest_tag(self):
        """The version is bumped with every tag (docs/project-setup.md, row "Tags"): a tag made
        without the bump would pin players to the version before it."""
        try:
            out = subprocess.run(["git", "tag", "-l", "v*"], cwd=ROOT, capture_output=True, text=True,
                                 timeout=30, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git not available")
        tags = [tuple(map(int, m.groups())) for t in out.split()
                if (m := re.match(r"v(\d+)\.(\d+)\.(\d+)", t))]
        if not tags:
            self.skipTest("no v* tags in this checkout")
        import yap_forever
        self.assertGreaterEqual(tuple(map(int, yap_forever.__version__.split("."))), max(tags))

    def test_skill_frontmatter(self):
        fm = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("name"), SKILL.name)
        self.assertTrue(0 < len(fm.get("description", "")) <= 1024)

    def test_skill_runs_the_planner_by_the_plugin_root(self):
        """Finding 8: the plugin root comes from ${CLAUDE_PLUGIN_ROOT}, never a guessed path, and
        each interpreter has an allowed-tools rule whose text is the command the skill writes."""
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        launcher = '"${CLAUDE_PLUGIN_ROOT}/yap-forever.py"'
        self.assertTrue((PLUGIN / "yap-forever.py").is_file())
        self.assertIn(f"`<python> {launcher} <command>`", text)
        rules = frontmatter_list(text, "allowed-tools")
        self.assertEqual(rules, [f"Bash({python} {launcher} *)" for python in ("python3", "python", "py -3")])
        for python in ("py -3", "python3", "python"):
            self.assertIn(f"`{python}`", text.split("## Workflow")[0])
        self.assertNotIn("two folders above", text)
        self.assertNotRegex(text, r"`cd [^`]*`")

    def test_references_use_the_planner_form(self):
        for ref in (SKILL / "references").glob("*.md"):
            body = ref.read_text(encoding="utf-8")
            self.assertNotIn("<python> -m yap_forever", body, ref.name)

    def test_named_sections_exist(self):
        """SKILL.md and the coverage page point to a rule by file and section ("Green crafts",
        step 2); every section named is in the file linked."""
        link = re.compile(r'\]\((?:references/)?([\w-]+\.md)\)((?:,? (?:and )?(?:step \d|"[^"]+"))*)')
        checked = 0
        for page in (SKILL / "SKILL.md", SKILL / "references" / "coverage.md"):
            for m in link.finditer(page.read_text(encoding="utf-8")):
                target = (SKILL / "references" / m.group(1)).read_text(encoding="utf-8")
                for name in re.findall(r'"([^"]+)"', m.group(2)):
                    self.assertRegex(target, rf"(?m)^(?:## |\*\*){re.escape(name)}",
                                     f"{page.name} -> {m.group(1)}: no heading {name!r}")
                    checked += 1
                for step in re.findall(r"step (\d)", m.group(2)):
                    self.assertIn(f"\n## {step}. ", target, f"{page.name} -> {m.group(1)}")
                    checked += 1
        self.assertGreaterEqual(checked, 12)

    def test_skill_keeps_questions_and_links_the_rules(self):
        """Finding 9: SKILL.md says what to ask and what to run; the rules live once in the references."""
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for rule in ("cash_gold", '"2/alliance"', "bound on pickup", "bag_slots", "reagent_slots",
                     "reports/<date>", "150, 225", "study_hint_gold_per_point", "listing depth"):
            self.assertNotIn(rule, text)
        self.assertIn("references/coverage.md", text)

    def test_milestones_are_the_expert_artisan_and_master_caps(self):
        """game-rules.md: a legacy talent point the first time a profession reaches 150, 225 and 300,
        the caps of the Expert, Artisan and Master ranks the planner trains."""
        from yap_forever.trainers import RANK_BY_CAP
        text = (SKILL / "references" / "game-rules.md").read_text(encoding="utf-8")
        m = re.search(r"\*\*Milestones:\*\* the first time a profession on the account reaches (\d+), (\d+) and (\d+)", text)
        caps = [c for c, rank in RANK_BY_CAP.items() if rank in ("Expert", "Artisan", "Master")]
        self.assertEqual([int(g) for g in m.groups()], sorted(caps))

    def test_skill_reference_links_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        refs = set(re.findall(r"references/[\w-]+\.md", text))
        self.assertGreaterEqual(len(refs), 3)
        for ref in refs:
            self.assertTrue((SKILL / ref).exists(), ref)

    def test_setup_shows_the_default_remote_command(self):
        from yap_forever import settings
        text = (SKILL / "references" / "setup.md").read_text(encoding="utf-8")
        self.assertIn(f'command = "{settings.REMOTE_COMMAND}"  # default, run there', text)

    def test_credits_cover_sources(self):
        credits = (PLUGIN / "CREDITS.md").read_text(encoding="utf-8")
        for url in gamedata.SOURCES.values():
            m = re.match(r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/", url)
            origin = m.group(1) if m else re.match(r"https://([^/]+)/", url).group(1)
            self.assertIn(origin, credits)
        for pin in (gamedata.SKILLUP_SHA, gamedata.QUESTIE_SHA, str(gamedata.WAGO_BUILD)):
            self.assertIn(pin, credits)

    def test_installs_ship_the_licence_and_credits(self):
        """An install copies only plugin/: the GPL text and the credits must be in it. The root
        LICENSE stays for GitHub's licence detection and must be the same file."""
        self.assertEqual((PLUGIN / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
        self.assertTrue((PLUGIN / "CREDITS.md").is_file())
        self.assertFalse((ROOT / "CREDITS.md").exists(), "one credits file, in plugin/")

    def test_tests_import_the_installed_package(self):
        import yap_forever
        self.assertEqual(Path(yap_forever.__file__).resolve().parent, PLUGIN / "yap_forever")

    def test_the_private_details_scan_covers_the_plugin(self):
        files = tracked_text_files()
        for path in (SKILL / "SKILL.md", PLUGIN / "yap_forever" / "cli.py", ROOT / "README.md"):
            self.assertIn(path, files)

    def test_no_private_details(self):
        deny_file = ROOT / ".private-denylist"
        deny = [l.strip() for l in deny_file.read_text(encoding="utf-8").splitlines()
                if l.strip()] if deny_file.exists() else []
        hits = []
        for p in tracked_text_files():
            text = p.read_text(encoding="utf-8", errors="replace")
            for label, rx in PRIVATE:
                if rx.search(text):
                    hits.append(f"{p.relative_to(ROOT)}: {label}")
            for d in deny:  # plain text, or "re:<pattern>" for things like a bare number
                found = re.search(d[3:], text) if d.startswith("re:") else d in text
                if found:
                    hits.append(f"{p.relative_to(ROOT)}: denylisted text")
        self.assertEqual(hits, [])

    def test_order_decision_documented(self):
        """#35: game-rules.md says the planner never reorders professions for disenchant skill-ups, and the
        60 it names is the last threshold of disenchant.toml."""
        import tomllib

        from yap_forever.config import STATIC_DIR
        text = (SKILL / "references" / "game-rules.md").read_text(encoding="utf-8")
        self.assertIn("never reorders", text)
        self.assertIn("41s", text)
        self.assertIn("under 1g", text.replace("\n", " ").replace("  ", " "))
        with open(STATIC_DIR / "disenchant.toml", "rb") as f:
            self.assertEqual(tomllib.load(f)["skill_ups"][-1], 60)
        self.assertIn("only up to 60", text.replace("\n", " ").replace("  ", " "))

    def test_docs_promise_budget(self):
        """#50: the skill offers a budget as a goal and asks how to share it; the references give the keys
        and the lines the guide prints (tests/test_budget.py and test_guide.py check them). #96: a budget covers a
        recipe goal; "not applied" is gone."""
        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        setup, skill = read("references/setup.md"), read("SKILL.md")
        coverage, layout = read("references/coverage.md"), read("references/list-layout.md")
        for key in ("budget = ", "budget_order = ", "--budget GOLD", "--order even|NAME,NAME"):
            self.assertIn(key, setup)
        step3 = skill[skill.index("3. **Ask the goal"):skill.index("4. **Refresh prices")]
        self.assertIn("evenly or one at a time", step3)
        self.assertIn("budget", step3)
        self.assertIn("[gold]", step3)
        self.assertNotIn("budget", coverage[coverage.index("Not yet"):])
        self.assertIn("75, 150, 225 and 300", setup)
        for line in ("<budget> takes <Profession> to <stop> (<gold>).",
                     "The next stop, <Profession> <stop>, costs about <gold> more.",
                     "<budget> doesn't reach the first stop: nothing is planned yet.",
                     "Nothing to craft within this budget.",
                     "; the route stops there: <why>.",
                     "<Profession> gets none of it: <why>.",
                     "Level one profession at a time: <first> first, then <second>.",
                     # #96: a budget covers a recipe goal (tests/test_budget.py RecipeGoalTests, RecipeGoalReportsTests)
                     "<budget> covers <Profession> to <skill> and one <recipe> (<gold>).",
                     "The goal, <Profession> <skill> and one <recipe>, costs about <gold> more.",
                     "<Profession> is not planned with this budget: it goes to the <Profession> goal.",
                     "Your <Person> <Name> can make the <n> <item> for about <gold> less than the AH and mail them; "
                     "the gold to bring doesn't count that.",
                     "first craft <n> <item> (your <Profession>)"):
            self.assertIn(line, layout)
        for text in (setup, layout, skill):
            self.assertNotIn("not applied", text)
        for promise in ("covers that profession's goal", "is not planned with the budget",
                        "first craft <n> <item> (your <Profession>)", "Two recipe targets are cut like two skill targets",
                        "not counted in \"Gold to bring\""):
            self.assertIn(promise, setup)
        self.assertIn("A budget covers a recipe goal too", step3)
        self.assertIn("`[skills]`", step3)
        from yap_forever import budget
        from yap_forever.gamedata import BS, ENCH
        self.assertEqual(budget.not_planned(ENCH, BS),
                         "Enchanting is not planned with this budget: it goes to the Blacksmithing goal.")

    def test_docs_promise_trainer_ranks(self):
        """#82: game-rules.md gives the rank caps trips.recipe_rank_cap uses and the Truesilver Rod sighting of
        seen_requirements.toml; list-layout.md gives the rows the guide prints (tests/test_guide.py VisitRowTests)."""
        from yap_forever import gamedata
        from yap_forever.trips import MAX_TRIP_ALTS, RANK_CAPS

        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        rules, layout, coverage = read("references/game-rules.md"), read("references/list-layout.md"), \
            read("references/coverage.md")
        self.assertEqual(RANK_CAPS, (75, 150, 225, 300))
        self.assertEqual(MAX_TRIP_ALTS, 3)  # "keep their own three", "only the costliest three recipe trips"
        self.assertIn("Journeyman to 75, Expert to 150, Artisan to 225, Master to 300", rules)
        self.assertIn("confirmed in game (2026-11-21)", rules)
        self.assertIn("from 1 up to", rules)
        self.assertIn("Expert trainers stop at 150", rules)
        self.assertNotIn("one sighting", rules)
        self.assertEqual(gamedata.load_seen_requirements()[14380], 184)
        self.assertIn("Truesilver Rod was learned at Blacksmithing 184, so it needs 175, not the inferred 200", rules)
        for line in ("While there, learn: <recipe> (<fee>), ...", "If you don't have them yet: <recipe>, ...",
                     "- **Before you start**, make sure you know: <recipes> (any <Rank> <Person> teaches them).",
                     "any <Rank> <Person>",
                     "- **Trip:** back to <trainer>, <place>, at <skill> for <recipes>",
                     "; or skip it: +<gold> for the route without it", "; there is no other way to reach the target without it",
                     "- At <skill>, learn <recipes> at any <Rank> <Person> in a capital (for example <name>, <capital>).",
                     "*At <skill>: start crafting <recipe> (learned at <trainer>)*", "(learned before you start)",
                     "- At <skill>, learn <recipes> at any <Rank> <Person> in a capital.",
                     "(learn it at <trainer> if you don't have it)",
                     "As with vendor trips, which keep their own three, only the costliest three recipe trips",
                     "a Favor trip, always a target's, gets no clause",
                     "a recipe needed at 240 and used then, and one at 245, make two rows",
                     "The bring list ends at the next rank trip, trip back for recipes or capital stop for recipes",
                     "(learned at <trainer>; listed from <skill> in the Forever data:",
                     "(learned before you start; listed from ...)"):
            self.assertIn(line, layout)
        self.assertNotIn("doesn't list", layout)  # a higher rank teaches every lower recipe: no fallback clause
        self.assertIn("trips back to them for recipes", coverage)

    def test_docs_promise_trainer_trips(self):
        """#82: setup.md gives the trainer_trips key, its values and default (profile.py); SKILL.md asks the question
        once per character and saves the answer; list-layout.md gives the rows the guide prints (tests/test_guide.py
        VisitRowTests, tests/test_shopping.py BringListTests)."""
        from yap_forever.profile import TRAINER_TRIPS, Character
        from yap_forever.shopping import CRAFT_ROOM

        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        setup, skill = read("references/setup.md"), read("SKILL.md")
        layout, coverage = read("references/list-layout.md"), read("references/coverage.md")
        self.assertEqual(TRAINER_TRIPS, ("as_needed", "one_go"))
        self.assertEqual(Character("Ana Brightforge").trainer_trips, "as_needed")
        self.assertIn('`trainer_trips`: `"as_needed"` (default) or `"one_go"`', setup)
        step5 = skill[skill.index("5. **Run the planner"):skill.index("6. **Walk through")]
        self.assertIn("level there in one go, or come back as needed?", step5)
        self.assertIn("once per character", step5)
        self.assertIn('`trainer_trips` under `[characters."Name"]` in `profile.toml`', step5)
        self.assertEqual(CRAFT_ROOM, 10)
        for line in ("Learn at the trainer as you reach them: <recipe> at <skill>, ...",
                     "<count> <item> (yours)",
                     "Made later by your <Profession> on this route: <count> <item>, ...: craft those rows before you "
                     "go, or buy them on the AH (about <gold>).",
                     "From disenchanting what your <Profession> makes later on this route: <count> <item>, ...: craft "
                     "those rows and disenchant the greens before you go, or buy them on the AH (about <gold>).",
                     "This needs <N> free slots and you have <M>: get bigger bags, bank what this stretch doesn't need, "
                     "or set a lower goal (for example <skill>) so it fits.",
                     "or set a lower goal so it fits.", "10 slots kept free for crafting",
                     "`trainer_trips = \"one_go\"`", "`1 <pattern> (from the AH)`", "`(from the bank)`",
                     "`(mail from <Name>)`", "gets no `**Trip:**` row of its own"):
            self.assertIn(line, layout)
        from yap_forever.shopping import PATTERN_FROM
        for text in PATTERN_FROM.values():  # #88: where a one-go bring list's pattern comes from
            self.assertIn(f"({text})", layout)
        self.assertIn("in one go", coverage)

    def test_docs_promise_runs_at_trainings(self):
        """#87, #91: list-layout.md says a run that crosses a rank training is two rows, one in each stage
        (tests/test_guide.py RunAcrossTrainingGuideTests, tests/test_shopping.py RunAtTrainingTests)."""
        layout = " ".join((SKILL / "references" / "list-layout.md").read_text(encoding="utf-8").split())
        self.assertIn("A run that crosses a rank training is two rows, one in each stage.", layout)

    def test_docs_promise_free_skips(self):
        """#90: list-layout.md gives the free-skip rule of plan.take_free_skips (trips.FREE_SKIP, MAX_TRIP_ALTS rounds)
        and the lines guide.free_skip_line prints (tests/test_trips.py FreeSkipTests, tests/test_cli.py
        FreeSkipReportTests); setup.md and coverage.md say a free trip is left out."""
        from yap_forever.trips import FREE_SKIP, MAX_TRIP_ALTS

        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        layout, setup, coverage = (read(f"references/{n}.md") for n in ("list-layout", "setup", "coverage"))
        self.assertEqual((FREE_SKIP, MAX_TRIP_ALTS), (0.5, 3))
        for line in ("A trip whose route-without costs at most 0.5c more (or less), reaches the same skills and makes "
                     "fewer trainer visits and pattern trips is left out of the route",
                     "at most three rounds, the recipes left out adding up",
                     "the trips left out cost at most 0.5c more together, against the route as first planned",
                     "each skip is also within 0.5c of the route it starts from",
                     "a route both guides share is planned without a trip only when it is free in both measures",
                     "`Planned without the trip back to <trainer> at <skill> for <recipes>: the route without it "
                     "costs the same.`",
                     "`Planned without the trip to buy the pattern for <recipe>: the route without it costs the same.`",
                     "A trip left on the route whose skip costs at most 0.5c more gets no skip clause."):
            self.assertIn(line, layout)
        self.assertNotIn("no extra cost", layout)
        self.assertIn("one that costs nothing to skip is left out of the route", setup)
        self.assertIn("a trip that costs nothing to skip is left out of the route", coverage)

    def test_docs_promise_favor_suggestions(self):
        """#95: game-rules.md says Merchant's Favor recipes never level a route and gives the level window of
        favor_suggest (LEVEL_WINDOW, LATE_WINDOW, LATE_FROM, GUIDE_LIMIT); list-layout.md gives the section the guide and the
        report print (tests/test_favor_suggest.py, test_guide.py CouldAlsoMakeGuideTests, test_report.py
        CouldAlsoMakeReportTests, test_cli.py CouldAlsoMakeWiringTests); coverage.md says it."""
        from yap_forever import favor_suggest as fs

        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        rules, layout, coverage = (read(f"references/{n}.md") for n in ("game-rules", "list-layout", "coverage"))
        self.assertIn("## Merchant's Favor", rules)
        for line in ("Merchant's Favor recipes are personal-use rewards: the planner never uses them to level, as "
                     "needed or in one go, and plans no trip to the Favor vendor for them.",
                     "A Favor recipe set as a recipe target is still planned",
                     f"within {fs.LEVEL_WINDOW} levels of the character's level (within {fs.LATE_WINDOW} from "
                     f"character level {fs.LATE_FROM})",
                     "an item with required level 0 (no requirement) has no level test, nor has an enchant, which "
                     "crafts no item",
                     "Without `level` in `stock.toml` only the items with no level requirement and the enchants are "
                     "suggested",
                     "the bank first, then by mail from the group's other characters, and the rest is bought at "
                     "today's AH or vendor price",
                     "A reagent with no price that nobody holds rules the recipe out."):
            self.assertIn(line, rules)
        self.assertEqual(fs.HEADING, "## You could also make")
        for line in (f"`{fs.HEADING}`", f"`{fs.INTRO}`", "`**You could also make**`",
                     "`- **<name>** (<Profession> <skill>, for level <level>): <favor> of your <Favor> Favor; "
                     "materials about <gold> on the AH, <n> <item> from your bank, <n> <item> (mail from <Name>).`",
                     "`(<Profession> <skill>)`", "`(<Profession> <skill>, any level)`", f"`{fs.NO_LEVEL_NOTE}`",
                     "a recipe with no reagents ends after `Favor`", "`from a vendor`", "`on the AH and from a vendor`",
                     "`materials: <n> <item> from your bank`",
                     f"The guide lists at most {fs.GUIDE_LIMIT} items, then at most {fs.GUIDE_LIMIT} enchants, each "
                     "kind followed by `and <n> more.` in a paragraph of its own when it is cut; the report lists them "
                     "all.",
                     "`Merchant's Favor recipes are not used to level (see You could also make).`",
                     "`Item required levels are not in the game data: Merchant's Favor items are not suggested, only "
                     "enchants.`"):
            self.assertIn(line, layout)
        self.assertEqual(tuple(fs.WHERE.values()), ("on the AH", "from a vendor", "on the AH and from a vendor"))
        self.assertIn("never used to level", coverage)
        self.assertIn("You could also make", coverage)

    def test_docs_promise_capital_key(self):
        """#98 (C25): setup.md gives the `capital` key, its six values by faction (profile.CAPITAL_NAMES, capital_names)
        and its default (plan.home_capital; tests/test_profile.py, test_trips.py HomeCapitalTests and
        CapitalStopTests, test_guide.py CapitalGuideTests, test_compare.py)."""
        from yap_forever.profile import Character, capital_names

        setup = " ".join((SKILL / "references" / "setup.md").read_text(encoding="utf-8").split())

        def choices(faction):
            names = [f'`"{n}"`' for n in capital_names(faction)]
            return ", ".join(names[:-1]) + " or " + names[-1]
        self.assertEqual(len(capital_names("alliance") + capital_names("horde")), 6)
        self.assertIsNone(Character("Ana Brightforge").capital)
        for line in ("Optional per character: `capital`, the capital the guide starts in (every capital has an AH, "
                     "mailbox and bank):",
                     f"{choices('alliance')} for Alliance, {choices('horde')} for Horde; another faction's capital, "
                     "or any other value, is refused.",
                     "Left out (default), the guide starts in the only capital the route's stages need",
                     "or, when two professions point to two capitals, in the one whose stage the route reaches first, "
                     "and it says how to start in the other",
                     "are capital stops, not trips, with no bring list, whatever `trainer_trips`",
                     "The other capital follows `trainer_trips`",
                     "Remote trainers (every Master, the Artisan Enchanters) stay trips.",
                     '"Trips away" counts the trips outside the capital the guide starts in.'):
            self.assertIn(line, setup)

    def test_docs_promise_home_capital(self):
        """#98: list-layout.md gives the rows the guide prints for the home capital and the other one, and game-rules.md
        where the Artisans and Masters stand (tests/test_guide.py CapitalGuideTests, test_trips.py CapitalStopTests,
        test_trainers.py StageCapitalTests)."""
        def read(name):
            return " ".join((SKILL / "references" / name).read_text(encoding="utf-8").split())
        layout, rules = read("list-layout.md"), read("game-rules.md")
        for line in ("every capital has an AH, mailbox and bank, so the player starts there",
                     "`Level <Profession> <from>–<to> in <City>: the <Rank> <Person> <name> (x, y) is there, with the "
                     "AH, mailbox and bank.` and the city's tip",
                     "In that capital the rank training and every visit back for recipes are stops, not trips, with no "
                     "bring list, as needed and in one go (one go never folds them)",
                     "`- At <skill>, in <City>: train <Profession> to <cap> at <name>.`",
                     "`- At <skill>, in <City>: learn <recipes> at <name>`, then the skip clause and a full stop.",
                     "`Planned without the stop at <skill> in <City> for <recipes>: the route without it costs the "
                     "same.`",
                     "`- At <skill>, learn <recipes> at any <Rank> <Person> in <City>.`",
                     "Its trip rows have no bring list and end `<City> has an AH, mailbox and bank: buy as you go "
                     "there.` and the city's tip.",
                     "`This route's <Rank> trainers are in <City A> (<Profession A>) and <City B> (<Profession B>). "
                     "This guide starts in <City A>; to start in <City B>, set capital = \"<key>\" for this "
                     "character in profile.toml.`",
                     "\"Trips away\" counts only the trips outside the home capital.",
                     "Remote trainers (every Master, the Artisan Enchanters) stay trips with their bring lists."):
            self.assertIn(line, layout)
        for line in ("every Master trainer stands outside the capitals, for both factions, and so do the Artisan "
                     "Enchanters (Elwynn Forest, Stonetalon Mountains)",
                     "for Alliance, Alchemy and Leatherworking in Darnassus, Blacksmithing and Engineering in Ironforge, "
                     "Tailoring in Stormwind; for Horde, Alchemy and Tailoring in Undercity, Blacksmithing and "
                     "Engineering in Orgrimmar, Leatherworking in Thunder Bluff.",
                     "Every capital has an AH, mailbox and bank, so the guide levels the stage of the capital it "
                     "starts in (the home capital) there; a stage in the other capital follows `trainer_trips`",
                     "Darnassus has no Blacksmithing or Engineering trainer, Thunder Bluff no Engineering one."):
            self.assertIn(line, rules)
        coverage = read("coverage.md")
        self.assertIn("an Artisan stage in the home capital is levelled there, its visits are capital stops, not trips away",
                      coverage)
        # 5b: the joined capital stops (trips.JOIN_SPAN; test_trips.py JoinStopTests, test_guide.py JoinedStopGuideTests)
        from yap_forever.profile import CAPITAL_NAMES
        from yap_forever.trainer_notes import load_notes
        from yap_forever.trips import JOIN_SPAN
        for line in (f"where the earlier stop is made, the later stop's profession is no more than {JOIN_SPAN} skill "
                     "points short of the later stop's skill",
                     "`- **Capital stop** at <Profession A> <skill> (in <City>): learn <recipes A> at <a|an> <Rank> "
                     "<Person A>, and <recipes B> at <a|an> <Rank> <Person B> (you use <it|them> from <Profession B> "
                     "<skill>).`",
                     "`(any capital, for example <City>)`",
                     "`<a|an> <Rank> <Person> (title unconfirmed in the data)`",
                     "from the stop to each one's next trainer visit as the guide shows it (a visit joined to a later "
                     "stop is made there, so no row is in two sentences)",
                     "`*At <skill>: start crafting <recipe> (learned at the capital stop at <Profession A> <skill>)*`",
                     "`The trade supplies vendor near the trainers sells the <count> <item>, ... these rows need.`",
                     "A stop alone keeps its row."):
            self.assertIn(line, layout)
        # the skill's question (C29): two capitals, each with its tip, then the other one's approach; one capital: none
        skill = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        step3 = skill[skill.index("3. **Ask the goal"):skill.index("4. **Refresh prices")]
        for line in ("ask **Start in <City A> (<Profession A>'s <Rank>) or <City B> (<Profession B>'s <Rank>)?**",
                     "with each capital's tip ([game-rules.md](references/game-rules.md), \"Trainers and ranks\")",
                     "for the other one, **level that stage there in one go, or go as needed?**",
                     "When the character already has `trainer_trips`, don't ask that again: say what it is set to, since "
                     "changing it changes the trips to the remote trainers too.",
                     "Save the answers as `capital` and `trainer_trips`",
                     "One `trainer_trips` answer covers both kinds of trip: the other capital and the remote trainers "
                     "(every Master, the Artisan Enchanters); tell the player so when you ask",
                     "With one capital, say where the guide starts and ask nothing."):
            self.assertIn(line, step3)
        tips, city = load_notes().cities, {zone: key.replace("_", " ").title() for key, zone in CAPITAL_NAMES.items()}
        self.assertGreaterEqual(len(tips), 2)
        self.assertIn("- **Capital tips** (`[cities]` in `trainer_notes.toml`, from play):", rules)
        for zone, tip in tips.items():
            self.assertIn(f"{city[zone]}: \"{tip}\"", rules)
        self.assertIn("One `trainer_trips` answer covers both kinds of trip: the stage in the other capital and the "
                      "remote trainers", rules)
        self.assertIn("The skill asks for it with `trainer_trips` when the route's stages are in two capitals "
                      "(SKILL.md, step 3)", read("setup.md"))

    def test_docs_promise_ah_rule(self):
        """#62: game-rules.md "Selling crafts" gives the AH rule with its numbers (costmodel.AH_UNIT_CAP, MIN_AH_MARGIN,
        BUYOUT_RATIO, the `ah_premium` default) and that AH resale of crafts never chooses the route; setup.md gives the
        key and its default (tests/test_costmodel.py AhPremiumTests, test_config.py, test_report.py
        AhSalesReportTests, test_guide.py SellClauseGuideTests)."""
        from yap_forever.config import Stock
        from yap_forever.costmodel import AH_UNIT_CAP, BUYOUT_RATIO, MIN_AH_MARGIN
        from yap_forever.guide import gold
        from yap_forever.prices import AH_CUT

        def read(name):
            return " ".join((SKILL / "references" / name).read_text(encoding="utf-8").split())
        rules, setup = read("game-rules.md"), read("setup.md")
        import dataclasses
        premium = next(f.default for f in dataclasses.fields(Stock) if f.name == "ah_premium")
        self.assertEqual((premium, gold(MIN_AH_MARGIN)), (2, "1s"))
        section = rules[rules.index("## Selling crafts"):rules.index("## Merchant's Favor")]
        for line in ("AH resale of crafts never chooses the route",
                     f"only when the AH pays, after its {AH_CUT:.0%} cut (the lowest listing less the cut)",
                     f"at least {premium:g}× its vendor price and {gold(MIN_AH_MARGIN)} more",
                     f"The {premium:g}× is `ah_premium` in `stock.toml` (a number, 1 or more; default {premium:g}).",
                     f"At most {AH_UNIT_CAP} of each craft count as sold on the AH",
                     "quest items count up to `quest_item_sales` (no limit when it is left out)",
                     "How many are listed today doesn't change that count.",
                     f"With only 1 or 2 listed at {BUYOUT_RATIO}× the vendor price or more"):
            self.assertIn(line, section)
        for line in (f"at least `ah_premium` times its vendor price and {gold(MIN_AH_MARGIN)} more",
                     f"`ah_premium` is a number, 1 or more, default {premium:g} when left out; anything else is "
                     "refused, naming the file and the key.",
                     f"At most {AH_UNIT_CAP} of each craft count as sold there",
                     "The day's count doesn't limit how many crafts count as sold"):
            self.assertIn(line, setup)

    def test_docs_promise_vendor_rule(self):
        """#97: game-rules.md "Selling crafts" says a craft's vendor price counts in choosing the route, next to PR 6's
        AH sentence; list-layout.md gives the route row's amount, the table's rows, Money and Totals, and setup.md the
        budget's fallback (tests/test_guide.py SellClauseGuideTests, test_compare.py, test_budget.py
        UncreditedFallbackTests)."""
        def read(name):
            return " ".join((SKILL / "references" / name).read_text(encoding="utf-8").split())
        rules, layout, setup = read("game-rules.md"), read("list-layout.md"), read("setup.md")
        section = rules[rules.index("## Selling crafts"):rules.index("## Merchant's Favor")]
        for line in ("AH resale of crafts never chooses the route",
                     "A craft's vendor price counts in choosing the route; AH resale of crafts never does."):
            self.assertIn(line, section)
        from yap_forever.compare import LEAST_GOLD_NOTE
        for line in ("→ sell to a vendor: about <gold> back", "the rest to a vendor: about <gold> back",
                     "less the crafts sold on the AH, which go to the item's first rows",
                     "`Gold out of pocket`, `Back from a vendor`, `Total value` (vendor sales only) and `AH sales on top` "
                     "(`—` when there are none)", LEAST_GOLD_NOTE,
                     "- **Back from selling crafts:** about <total>: <vendor> from vendors (counted in choosing the "
                     "route) and about <ah> more if the AH sales go through.",
                     "- **Back from selling crafts:** about <vendor> from vendors (counted in choosing the route).",
                     "`Back from vendors: <gold> (counted in choosing the route).`",
                     "`AH sales on top: <gold> (not counted).`",
                     "(left out in choosing this route, to fit the budget)"):
            self.assertIn(line, layout)
        self.assertIn("each stop takes the route planned with what vendors pay back when its gold fits, else the route "
                      "planned without it when that one fits and gets each profession as far; the stop is reached when "
                      "either fits.", setup)


    def test_docs_promise_two_ways_to_pay(self):
        """#97 part 3: game-rules.md says what "Gold to bring" is and that selling crafts as you go needs less up front;
        setup.md gives the `pay` key and flag, list-layout.md the shopping list's line, and SKILL.md asks the question
        when the player gives a budget (tests/test_shopping.py AsYouGoTests, test_budget.py PayTests, test_config.py)."""
        def read(name):
            return " ".join((SKILL / name).read_text(encoding="utf-8").split())
        rules, setup = read("references/game-rules.md"), read("references/setup.md")
        layout, skill = read("references/list-layout.md"), read("SKILL.md")
        section = rules[rules.index("## Selling crafts"):rules.index("## Merchant's Favor")]
        self.assertIn("Gold to bring is the gold to buy everything before you start. Selling crafts to a vendor as you "
                      "go needs less up front; the shopping list says how much, and a budget can use either (pay).",
                      section)
        for key in ('pay = "upfront"', '"as_you_go"', "--pay upfront|as_you_go"):
            self.assertIn(key, setup)
        from yap_forever.shopping import AS_YOU_GO_LINE
        self.assertIn(AS_YOU_GO_LINE.format("<gold>", "<gold>"), layout)
        self.assertIn("`; planned to your <budget> budget, selling crafts to a vendor as you go`", layout)
        step3 = skill[skill.index("3. **Ask the goal"):skill.index("4. **Refresh prices")]
        self.assertIn("Buy everything before you start, or sell crafts to a vendor as you go? Selling as you go needs "
                      "about Z less up front.", step3)
        self.assertIn("`pay`", step3)
        self.assertIn("save it under `[goals]` only together with a saved `budget` (`pay` alone is refused)", step3)
        # Z comes from a plan to the targets without the budget, so the question is asked even when the budget reaches
        # no stop up front (that cut route has no rows, so no line); only a plan with no line skips it
        for rule in ("first plan to the targets without it (no `--budget`, before a budget is saved under `[goals]`)",
                     "Whenever that line is there, ask once:",
                     "With no such line both ways need the same gold: keep the default. Then plan with the budget and "
                     "the chosen `--pay`."):
            self.assertIn(rule, step3)
        self.assertNotIn("after a first plan with that budget", step3)
        self.assertIn("`<budget> takes <Profession> to <stop> (<gold>, selling crafts to a vendor as you go).`", layout)
        self.assertIn("A remote trip's bring list buys its stretch before the trip", layout)
        self.assertIn("[--pay upfront|as_you_go]", skill)
        from yap_forever.config import PAYS
        self.assertEqual(PAYS, ("upfront", "as_you_go"))

if __name__ == "__main__":
    unittest.main()


# Commits up to and including this one may carry the owner's personal email (published before
# the noreply switch on 2026-11-18); every later commit by the owner must use a noreply address.
# Outside contributors' commits are theirs to sign as they like and are not checked.
IDENTITY_BASELINE = "8583233"
OWNER_LOGIN = "sableon"  # the repository owner's GitHub login (public in the repository URL)


def non_noreply(emails: list[str]) -> list[str]:
    return sorted({e for e in emails if e and "noreply" not in e})


def owner_names(authors: list[tuple[str, str]]) -> set[str]:
    """Names the owner commits under: those used with the owner's GitHub noreply address."""
    suffix = f"+{OWNER_LOGIN}@users.noreply.github.com"
    return {name for name, email in authors if email.endswith(suffix)}


def owner_leaks(rows: list[tuple[str, str, str, str]], names: set[str]) -> list[str]:
    """Non-noreply addresses on the owner's side of (author, author email, committer, committer email)."""
    return non_noreply([e for an, ae, cn, ce in rows for n, e in ((an, ae), (cn, ce)) if n in names])


class CommitIdentityTests(unittest.TestCase):
    def test_only_owner_commits_must_use_noreply(self):
        personal = "x" + "@" + "mail.example"
        owner_noreply = "1+" + OWNER_LOGIN + "@users.noreply.github.com"
        rows = [("Owner Name", owner_noreply, "GitHub", "noreply@github.com"),
                ("Some Contributor", personal, "Some Contributor", personal),
                ("Owner Name", personal, "Owner Name", personal)]
        names = owner_names([("Owner Name", owner_noreply), ("Some Contributor", personal)])
        self.assertEqual(names, {"Owner Name"})
        self.assertEqual(owner_leaks(rows, names), [personal])

    def test_non_noreply_flags_personal_addresses(self):
        personal = "x" + "@" + "mail.example"  # built up so the private-details scan ignores it
        self.assertEqual(non_noreply(["1+a@users.noreply.github.com", "noreply@github.com", personal]),
                         [personal])

    def test_commits_after_baseline_use_noreply(self):
        have = subprocess.run(["git", "cat-file", "-e", IDENTITY_BASELINE + "^{commit}"], cwd=ROOT,
                              capture_output=True)
        if have.returncode != 0:
            self.skipTest("shallow clone without the baseline commit")
        # On a pull_request run, HEAD is GitHub's throwaway test merge; check the PR's own commits
        # (its second parent). The real merge onto main is checked by the push run that follows.
        tip = "HEAD^2" if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" else "HEAD"
        def log(rng, fmt):
            out = subprocess.run(["git", "log", *rng, f"--format={fmt}"], cwd=ROOT, capture_output=True,
                                 text=True, encoding="utf-8", check=True).stdout
            return [tuple(line.split("\t")) for line in out.splitlines() if line]

        names = owner_names(log([tip], "%an%x09%ae") + log([tip], "%cn%x09%ce"))
        rows = log([f"{IDENTITY_BASELINE}..{tip}"], "%an%x09%ae%x09%cn%x09%ce")
        self.assertEqual(len(owner_leaks(rows, names)), 0,
                         "a commit after the baseline uses a personal email: set the repo's user.email "
                         "to your GitHub noreply address and turn on 'Keep my email private'")
