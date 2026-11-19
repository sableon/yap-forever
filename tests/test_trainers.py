import tempfile
import unittest
import unittest.mock
from pathlib import Path

from yap_forever import gamedata, settings, trainers
from yap_forever.trainers import Services, Trainer

FIX = Path(__file__).parent / "fixtures" / "gamedata"
BS, ENCH, LW, TAILOR, ALCH = 164, 333, 165, 197, 171


def fixture_data():
    return trainers.load_trainer_data(FIX)


class LoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_data()
        cls.by_id = {t.npc_id: t for t in cls.data.trainers}

    def test_master_blacksmith_row(self):
        t = self.by_id[90001]
        self.assertEqual(t, Trainer(90001, "Brakka Ironfold", BS, "Master", "AH", 33, (30, 70), True,
                                    "Master Blacksmith"))

    def test_rank_from_each_title(self):
        self.assertEqual(self.by_id[90002].rank, "Artisan")
        self.assertEqual(self.by_id[90003].rank, "Expert")
        self.assertEqual(self.by_id[90004].rank, "Journeyman")
        self.assertEqual(self.by_id[90004].profession, TAILOR)

    def test_first_spawn_in_the_home_zone(self):
        self.assertEqual((self.by_id[90002].zone, self.by_id[90002].coords), (1519, (60.5, 40.25)))
        # spawns in two zones: the NPC's own zoneID wins
        self.assertEqual((self.by_id[90017].zone, self.by_id[90017].coords), (1537, (20, 20)))

    def test_first_placed_spawn_is_used(self):
        rows = trainers.parse_npc_rows("""QuestieDB.npcData = [[return {
[1] = {'Late Placed',1,1,1,1,0,{[12]={{-1,-1},{7,8}}},nil,12,nil,nil,12,"A","Master Tailor",17},
}]]""")
        (t,) = trainers.load_trainers(rows)
        self.assertEqual(t.coords, (7, 8))

    def test_instance_trainer_has_no_coordinates(self):
        t = self.by_id[90006]
        self.assertEqual((t.zone, t.coords, t.rank), (1337, None, "Master"))

    def test_odd_title_has_profession_but_no_rank(self):
        t = self.by_id[90005]
        self.assertEqual((t.profession, t.rank, t.title_confirmed), (TAILOR, "", False))

    def test_titles_with_a_rank_but_not_the_usual_wording(self):
        t = self.by_id[90019]  # "Journeyman Alchemist Trainer"
        self.assertEqual((t.profession, t.rank, t.title_confirmed), (ALCH, "Journeyman", False))
        t = self.by_id[90018]  # "Expert Leathercrafter"
        self.assertEqual((t.profession, t.rank, t.title_confirmed), (LW, "Expert", False))

    def test_confirmed_titles(self):
        for npc in (90001, 90002, 90003, 90004, 90006):
            self.assertTrue(self.by_id[npc].title_confirmed, npc)

    def test_not_crafting_trainers_are_left_out(self):
        self.assertNotIn(90008, self.by_id)  # Mage Trainer
        self.assertNotIn(90007, self.by_id)  # a specialisation master, not the rank trainer
        self.assertNotIn(90010, self.by_id)  # a banker, not a trainer

    def test_placeholder_without_a_spawn_is_left_out(self):
        self.assertNotIn(90009, self.by_id)

    def test_escaped_quotes_in_names(self):
        rows = trainers.parse_npc_rows(r"""QuestieDB.npcData = [[return {
[1] = {'Ol\'Mirra "Scales"',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,"A","Master Tailor",17},
}]]""")
        (t,) = trainers.load_trainers(rows)
        self.assertEqual(t.name, 'Ol\'Mirra "Scales"')

    def test_accepts_text_or_parsed_rows(self):
        text = (FIX / "foreverNpcDB.lua").read_text(encoding="utf-8")
        self.assertEqual(trainers.load_trainers(text), trainers.load_trainers(trainers.parse_npc_rows(text)))

    def test_trainer_flag_is_required(self):
        rows = trainers.parse_npc_rows("""QuestieDB.npcData = [[return {
[1] = {'Not A Trainer',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,"A","Master Tailor",0},
[2] = {'No Flags',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,"A","Master Tailor",nil},
}]]""")
        self.assertEqual(trainers.load_trainers(rows), [])

    def test_damaged_file_says_what_to_do(self):
        text = (FIX / "foreverNpcDB.lua").read_text(encoding="utf-8")
        for bad in (text[: len(text) // 2], "nothing here"):
            with self.assertRaises(ValueError) as cm:
                trainers.parse_npc_rows(bad)
            self.assertIn("damaged", str(cm.exception))

    def test_file_that_is_not_utf8_is_damaged(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("foreverNpcDB.lua", "foreverObjectDB.lua", "AreaTable.csv"):
                (Path(d) / name).write_bytes((FIX / name).read_bytes())
            for name in ("foreverNpcDB.lua", "foreverObjectDB.lua"):
                good = (Path(d) / name).read_bytes()
                (Path(d) / name).write_bytes(good + b"\xff\xfe")
                with self.assertRaises(ValueError) as cm:
                    trainers.load_trainer_data(Path(d))
                self.assertIn(name, str(cm.exception))
                self.assertIn("damaged", str(cm.exception))
                (Path(d) / name).write_bytes(good)

    def test_missing_files_are_a_file_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                trainers.load_trainer_data(Path(d))

    def test_damaged_file_on_disk_names_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("foreverNpcDB.lua", "foreverObjectDB.lua", "AreaTable.csv"):
                (Path(d) / name).write_text((FIX / name).read_text(encoding="utf-8"), encoding="utf-8")
            (Path(d) / "foreverObjectDB.lua").write_text("QuestieDB.objectData = [[return {", encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                trainers.load_trainer_data(Path(d))
            self.assertIn("foreverObjectDB.lua", str(cm.exception))
            self.assertIn("damaged", str(cm.exception))


class ChooseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all = fixture_data().trainers

    def ids(self, prof, rank, faction):
        return [t.npc_id for t in trainers.trainers_for(self.all, prof, rank, faction)]

    def test_neutral_trainer_serves_both_sides(self):
        self.assertIn(90001, self.ids(BS, "Master", "alliance"))
        self.assertIn(90001, self.ids(BS, "Master", "horde"))

    def test_side_only_trainer_is_for_that_side(self):
        self.assertEqual(self.ids(BS, "Artisan", "alliance"), [90002, 90017])
        self.assertEqual(self.ids(BS, "Artisan", "horde"), [])  # the caller says so plainly
        self.assertEqual(self.ids(BS, "Expert", "horde"), [90003])
        self.assertEqual(self.ids(BS, "Expert", "alliance"), [])

    def test_unconfirmed_titles_sort_after_confirmed_ones_of_the_same_rank(self):
        mk = lambda i, ok: Trainer(i, "n", BS, "Expert", "AH", 1519, (1, 1), ok)
        got = trainers.trainers_for([mk(1, False), mk(2, True), mk(3, False)], BS, "Expert", "alliance")
        self.assertEqual([t.npc_id for t in got], [2, 1, 3])

    def test_rank_less_trainer_is_offered_for_every_rank_after_the_confirmed(self):
        self.assertEqual(self.ids(TAILOR, "Journeyman", "alliance"), [90004, 90005])
        self.assertEqual(self.ids(TAILOR, "Master", "horde"), [90005])

    def test_other_professions_are_not_mixed_in(self):
        self.assertEqual(self.ids(ENCH, "Master", "horde"), [90006])
        self.assertEqual(self.ids(ENCH, "Expert", "horde"), [])

    def test_unknown_faction_or_rank(self):
        with self.assertRaises(ValueError):
            trainers.trainers_for(self.all, BS, "Master", "neutral")
        with self.assertRaises(ValueError):
            trainers.trainers_for(self.all, BS, "Grand", "horde")

    def test_rank_for_cap(self):
        self.assertEqual([trainers.rank_for_cap(c) for c in (75, 150, 225, 300)],
                         ["Journeyman", "Expert", "Artisan", "Master"])
        with self.assertRaises(ValueError):
            trainers.rank_for_cap(100)


class NearbyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_data()
        cls.by_id = {t.npc_id: t for t in cls.data.trainers}

    def near(self, npc, radius=trainers.NEARBY_RADIUS):
        return trainers.nearby(self.by_id[npc], self.data.npc_rows, self.data.mailboxes, radius)

    def test_banker_auctioneer_and_mailbox_inside_the_radius(self):
        self.assertEqual(self.near(90001), Services(bank=True, auction=True, mail=True))

    def test_outside_the_radius(self):
        # the banker at (31, 71) is ~1.41 away, the auctioneer at (29, 69.5) ~1.12, the mailbox ~0.71
        self.assertEqual(self.near(90001, radius=1.0), Services(False, False, True))
        self.assertEqual(self.near(90001, radius=0.5), Services(False, False, False))
        self.assertEqual(self.near(90001, radius=1.2), Services(False, True, True))
        self.assertEqual(self.near(90001, radius=1.5), Services(True, True, True))

    def test_only_the_same_zone_counts(self):
        # the Stormwind trainer sees the Stormwind banker at (61, 41.5), not the auctioneer at (30, 70)
        self.assertEqual(self.near(90002), Services(bank=True, auction=False, mail=False))

    def test_trainer_without_coordinates_has_no_services(self):
        self.assertEqual(self.near(90006), Services(False, False, False))

    def test_unplaced_service_npcs_are_ignored(self):
        # the banker "placed" at (-1, -1) is ~1.4 from (0, 0) but has no position
        t = Trainer(1, "x", BS, "Master", "AH", 33, (0.0, 0.0), True)
        self.assertEqual(trainers.nearby(t, self.data.npc_rows, self.data.mailboxes, 2),
                         Services(False, False, False))

    def test_mailbox_in_the_trainers_zone_only(self):
        # (10, 10) mailbox in Stormwind is far from the Stormwind trainer at (60.5, 40.25)
        self.assertFalse(self.near(90002).mail)
        # the wandering trainer is in Ironforge (zone 1537) at (20, 20); the mailbox there is at (50, 50)
        self.assertFalse(self.near(90017).mail)
        self.assertTrue(trainers.nearby(self.by_id[90017], self.data.npc_rows, self.data.mailboxes, 50).mail)

    def test_non_mailbox_objects_and_unplaced_mailboxes_do_not_count(self):
        boxes = trainers.load_mailboxes((FIX / "foreverObjectDB.lua").read_text(encoding="utf-8"))
        self.assertEqual(sorted(boxes), [(33, 30.5, 69.5), (1519, 10, 10), (1537, 50, 50)])

    def test_radius_is_a_named_constant(self):
        self.assertGreater(trainers.NEARBY_RADIUS, 0)


class ZoneNameTests(unittest.TestCase):
    def test_names_from_the_area_table(self):
        names = trainers.load_zone_names(FIX / "AreaTable.csv")
        self.assertEqual(trainers.zone_name(33, names), "Stranglethorn Vale")
        self.assertEqual(trainers.zone_name(1337, names), "Uldaman")

    def test_unknown_zone_is_never_empty(self):
        self.assertEqual(trainers.zone_name(99999, {}), "zone 99999")

    def test_default_without_a_cache_file_falls_back(self):
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(settings, "paths", return_value=settings.Paths(Path(d))):
            self.assertEqual(trainers.zone_name(1519), "zone 1519")

    def test_default_reads_the_players_cache(self):
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(settings, "paths", return_value=settings.Paths(Path(d))):
            paths = settings.paths()
            paths.gamedata.mkdir(parents=True)
            (paths.gamedata / "AreaTable.csv").write_text((FIX / "AreaTable.csv").read_text(encoding="utf-8"),
                                                          encoding="utf-8")
            self.assertEqual(trainers.zone_name(1519), "Stormwind City")

    def test_zone_names_ship_in_the_pinned_sources(self):
        self.assertIn("AreaTable.csv", gamedata.SOURCES)
        self.assertIn(gamedata.WAGO_BUILD, gamedata.SOURCES["AreaTable.csv"])


class SourcesTests(unittest.TestCase):
    def test_npc_and_object_dbs_are_pinned_downloads(self):
        for name in ("foreverNpcDB.lua", "foreverObjectDB.lua"):
            self.assertIn(gamedata.QUESTIE_SHA, gamedata.SOURCES[name])
            self.assertTrue(gamedata.SOURCES[name].endswith("/data/Forever/" + name), name)


class InferredSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gd = gamedata.load_gamedata(FIX)

    def test_inferred_skill_read_from_trainer_lua(self):
        self.assertEqual(self.gd.recipes[2661].inferred_skill, 35)

    def test_recipe_without_an_inferred_skill(self):
        self.assertIsNone(self.gd.recipes[2660].inferred_skill)
        self.assertIsNone(self.gd.recipes[9999].inferred_skill)

    def test_required_skill_unchanged_by_inferred_skill(self):
        self.assertEqual(self.gd.recipes[2661].required_skill, 30)

    def test_trainer_file_without_the_table(self):
        with tempfile.TemporaryDirectory() as d:
            for p in FIX.iterdir():
                (Path(d) / p.name).write_bytes(p.read_bytes())
            text = (Path(d) / "Trainer.lua").read_text(encoding="utf-8")
            (Path(d) / "Trainer.lua").write_text(text.split("ns.TrainerInferred")[0], encoding="utf-8")
            gd = gamedata.load_gamedata(Path(d))
        self.assertIsNone(gd.recipes[2661].inferred_skill)


if __name__ == "__main__":
    unittest.main()
