import tempfile
import unittest
import unittest.mock
from pathlib import Path

from yap_forever import gamedata, settings, trainer_notes, trainer_text, trainers
from yap_forever.trainer_notes import Notes, TrainerNote
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


def _npc_text(*rows):
    return "QuestieDB.npcData = [[return {\n" + "\n".join(rows) + "\n}]]"


GOOD_ROW = "[1] = {'Good One',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,\"A\",\"Master Tailor\",17},"


class BadRowTests(unittest.TestCase):
    """A row with a wrong value type is skipped; the rest of the data still loads."""

    def load(self, bad_row):
        rows = trainers.parse_npc_rows(_npc_text(GOOD_ROW, bad_row))
        return [t.npc_id for t in trainers.load_trainers(rows)]

    def test_string_coordinates(self):
        self.assertEqual(self.load("[2] = {'X',1,1,1,1,0,{[12]={{\"a\",\"b\"}}},nil,12,nil,nil,12,\"A\","
                                   "\"Master Tailor\",17},"), [1])

    def test_string_flags(self):
        self.assertEqual(self.load("[2] = {'X',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,\"A\","
                                   "\"Master Tailor\",\"x\"},"), [1])

    def test_a_number_in_place_of_spawn_points(self):
        self.assertEqual(self.load("[2] = {'X',1,1,1,1,0,{[12]=5},nil,12,nil,nil,12,\"A\","
                                   "\"Master Tailor\",17},"), [1])

    def test_a_list_as_the_zone(self):
        self.assertEqual(self.load("[2] = {'X',1,1,1,1,0,{[12]={{1,2}}},nil,{1,2},nil,nil,12,\"A\","
                                   "\"Master Tailor\",17},"), [1])

    def test_a_number_as_the_faction_sides(self):
        self.assertEqual(self.load("[2] = {'X',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,7,"
                                   "\"Master Tailor\",17},"), [1])

    def test_a_number_as_the_name(self):
        self.assertEqual(self.load("[2] = {5,1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,\"A\","
                                   "\"Master Tailor\",17},"), [1])

    def test_nearby_ignores_service_rows_of_the_wrong_types(self):
        rows = trainers.parse_npc_rows(_npc_text(
            "[2] = {'Bank',1,1,1,1,0,{[12]={{\"a\",2}}},nil,12,nil,nil,12,\"A\",\"Banker\",256},",
            "[3] = {'Bank2',1,1,1,1,0,{[12]=5},nil,12,nil,nil,12,\"A\",\"Banker\",256},",
            "[4] = {'Bank3',1,1,1,1,0,{[12]={{1,2}}},nil,12,nil,nil,12,\"A\",\"Banker\",\"x\"},"))
        t = Trainer(1, "T", TAILOR, "Master", "A", 12, (1, 2), True)
        near = trainers.nearby(t, rows, [(12, 1, 2)], 5.0)
        self.assertEqual(near, Services(False, False, True))  # only the mailbox counts

    def test_a_bad_mailbox_row_is_skipped(self):
        boxes = trainers.load_mailboxes(
            "QuestieDB.objectData = [[return {\n"
            "[1] = {\"Mailbox\",1,1,{[12]=5}},\n[2] = {\"Mailbox\",1,1,{[12]={{\"a\",1},{3,4}}}},\n}]]")
        self.assertEqual(boxes, [(12, 3, 4)])

    def test_load_trainer_data_turns_type_errors_into_the_damaged_message(self):
        for exc in (TypeError, KeyError, IndexError):
            with unittest.mock.patch("yap_forever.trainers.load_trainers", side_effect=exc("x")):
                with self.assertRaises(ValueError) as cm:
                    trainers.load_trainer_data(FIX)
            self.assertIn("damaged", str(cm.exception), exc)


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
        # the only auctioneer in that zone is friendly to both factions: a neutral one
        self.assertEqual(self.near(90001), Services(bank=True, auction=True, mail=True, neutral_auction=True))

    def test_outside_the_radius(self):
        # the banker at (31, 71) is ~1.41 away, the auctioneer at (29, 69.5) ~1.12, the mailbox ~0.71
        self.assertEqual(self.near(90001, radius=1.0), Services(False, False, True))
        self.assertEqual(self.near(90001, radius=0.5), Services(False, False, False))
        self.assertEqual(self.near(90001, radius=1.2), Services(False, True, True, True))
        self.assertEqual(self.near(90001, radius=1.5), Services(True, True, True, True))

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


def _near(trainer_at, *service_rows, mailboxes=()):
    filler = "[99] = {'Peddler',1,1,1,1,0,{[12]={{1,1}}},nil,12,nil,nil,12,\"A\",\"Vendor\",4},"  # an empty table is not parsed
    rows = trainers.parse_npc_rows(_npc_text(filler, *service_rows))
    t = Trainer(1, "T", TAILOR, "Master", "A", 12, trainer_at, True)
    return t, rows, list(mailboxes)


def _auctioneer(npc, sides, x, y, zone=12):
    return (f"[{npc}] = {{'Auc{npc}',1,1,1,1,0,{{[{zone}]={{{{{x},{y}}}}}}},nil,{zone},nil,nil,12,\"{sides}\","
            "\"Auctioneer\",4097},")


class NeutralAuctionTests(unittest.TestCase):
    def near(self, *rows):
        t, npcs, boxes = _near((10, 10), *rows)
        return trainers.nearby(t, npcs, boxes, 5.0)

    def test_an_auctioneer_for_both_factions_is_neutral(self):
        got = self.near(_auctioneer(2, "AH", 11, 10))
        self.assertEqual((got.auction, got.neutral_auction), (True, True))

    def test_a_faction_auctioneer_is_not(self):
        for sides in ("A", "H"):
            got = self.near(_auctioneer(2, sides, 11, 10))
            self.assertEqual((got.auction, got.neutral_auction), (True, False), sides)

    def test_a_faction_auctioneer_next_to_a_neutral_one_makes_it_a_plain_auction_house(self):
        got = self.near(_auctioneer(2, "AH", 11, 10), _auctioneer(3, "A", 12, 10))
        self.assertEqual((got.auction, got.neutral_auction), (True, False))

    def test_a_neutral_auctioneer_out_of_range_does_not_count(self):
        got = self.near(_auctioneer(2, "A", 11, 10), _auctioneer(3, "AH", 40, 40))
        self.assertEqual((got.auction, got.neutral_auction), (True, False))

    def test_no_auction_house_is_not_neutral(self):
        self.assertFalse(self.near().neutral_auction)

    def test_an_empty_friendly_field_is_for_both(self):  # the loader reads a missing field as "AH" too
        row = "[2] = {'Auc',1,1,1,1,0,{[12]={{11,10}}},nil,12,nil,nil,nil,nil,\"Auctioneer\",4097},"
        self.assertTrue(self.near(row).neutral_auction)

    def test_booty_bay_style_fixture_trainer_has_a_neutral_auction_house(self):
        data = fixture_data()
        t = next(t for t in data.trainers if t.npc_id == 90001)
        self.assertTrue(trainers.nearby(t, data.npc_rows, data.mailboxes, trainers.NEARBY_RADIUS).neutral_auction)


class ClosestServiceTests(unittest.TestCase):
    def closest(self, at, *rows, mailboxes=(), zone=12):
        t, npcs, boxes = _near(at, *rows, mailboxes=mailboxes)
        t = Trainer(1, "T", TAILOR, "Master", "A", zone, at, True)
        return trainers.closest_service(t, npcs, boxes)

    BANK = "[5] = {'Bank',1,1,1,1,0,{[12]={{%s,%s}}},nil,12,nil,nil,12,\"A\",\"Banker\",256},"

    def test_the_nearest_of_the_three(self):
        self.assertEqual(self.closest((10, 10), self.BANK % (30, 10), mailboxes=[(12, 10, 60)]),
                         trainers.Closest("bank", False))
        self.assertEqual(self.closest((10, 10), self.BANK % (30, 10), mailboxes=[(12, 10, 20)]),
                         trainers.Closest("mailbox", False))
        self.assertEqual(self.closest((10, 10), self.BANK % (60, 10), _auctioneer(2, "A", 10, 40)),
                         trainers.Closest("auction", False))

    def test_a_neutral_auction_house_says_so(self):
        self.assertEqual(self.closest((10, 10), _auctioneer(2, "AH", 10, 40)), trainers.Closest("auction", True))

    def test_the_closest_auctioneer_decides_neutral(self):
        got = self.closest((10, 10), _auctioneer(2, "A", 10, 30), _auctioneer(3, "AH", 10, 50))
        self.assertEqual(got, trainers.Closest("auction", False))

    def test_only_the_same_zone_counts(self):
        self.assertIsNone(self.closest((10, 10), mailboxes=[(13, 11, 11)]))
        self.assertIsNone(self.closest((10, 10), _auctioneer(2, "A", 11, 11, zone=13)))

    def test_nothing_in_the_zone(self):
        self.assertIsNone(self.closest((10, 10)))

    def test_unplaced_services_do_not_count(self):
        self.assertIsNone(self.closest((10, 10), self.BANK % (-1, -1)))

    def test_a_trainer_without_coordinates_has_none(self):
        t = Trainer(1, "T", TAILOR, "Master", "A", 12, None, True)
        self.assertIsNone(trainers.closest_service(t, {}, [(12, 1, 1)]))

    def test_a_tie_goes_to_the_mailbox_then_the_bank(self):
        self.assertEqual(self.closest((10, 10), self.BANK % (10, 30), mailboxes=[(12, 10, 30)]).kind, "mailbox")
        self.assertEqual(self.closest((10, 10), self.BANK % (10, 30), _auctioneer(2, "A", 10, 30)).kind, "bank")


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

    def test_parent_zone_only_when_it_is_a_zone(self):
        data = fixture_data()
        self.assertEqual(data.parent_zone(9001), 9000)  # Hollow Depths lies inside Misty Vale
        self.assertIsNone(data.parent_zone(1337))  # no parent in the data
        self.assertIsNone(data.parent_zone(9000))
        data.parents[9002] = 9001  # a parent that is itself a sub-area is not a zone
        data.zones[9002] = "Deep Hollow"
        self.assertIsNone(data.parent_zone(9002))

    def test_zone_names_ship_in_the_pinned_sources(self):
        self.assertIn("AreaTable.csv", gamedata.SOURCES)
        self.assertIn(gamedata.WAGO_BUILD, gamedata.SOURCES["AreaTable.csv"])


class CapitalTests(unittest.TestCase):
    def test_capitals_by_faction(self):
        self.assertTrue({1519, 1537, 1657} <= set(trainers.CAPITALS["alliance"]))
        self.assertTrue({1637, 1638, 1497} <= set(trainers.CAPITALS["horde"]))
        self.assertFalse(set(trainers.CAPITALS["alliance"]) & set(trainers.CAPITALS["horde"]))


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


class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_data()

    def info(self, faction):
        return trainer_text.TrainerInfo(faction, self.data)

    def test_services_wording(self):
        f = trainer_text.services_text
        self.assertEqual(f(Services(True, False, True)), "Nearby: bank, mailbox; no auction house.")
        self.assertEqual(f(Services(True, True, True)), "Nearby: bank, auction house, mailbox.")
        self.assertEqual(f(Services(False, True, False)), "Nearby: auction house; no bank or mailbox.")
        self.assertEqual(f(Services(False, False, False)), "Nearby: none (no bank, auction house or mailbox).")

    NEUTRAL = "neutral AH (its own prices and a higher deposit)"

    def test_remote_stop_with_coordinates(self):
        stop = trainer_text.remote_stop(self.info("alliance"), BS, 300)
        self.assertTrue(stop.found)
        # the fixture's only auctioneer near Brakka serves both factions
        self.assertEqual(stop.text, "Brakka Ironfold, Stranglethorn Vale (30.0, 70.0). "
                                    f"Nearby: bank, {self.NEUTRAL}, mailbox.")

    def test_a_neutral_auction_house_is_named_so_in_every_position(self):
        f = trainer_text.services_text
        self.assertEqual(f(Services(True, True, True, True)), f"Nearby: bank, {self.NEUTRAL}, mailbox.")
        self.assertEqual(f(Services(False, True, False, True)), f"Nearby: {self.NEUTRAL}; no bank or mailbox.")
        self.assertEqual(f(Services(True, True, True, False)), "Nearby: bank, auction house, mailbox.")

    def test_nothing_near_says_the_closest(self):
        f = trainer_text.services_text
        none = Services(False, False, False)
        self.assertEqual(f(none, trainers.Closest("mailbox")),
                         "Nearby: nothing within a short walk; the closest is the mailbox.")
        self.assertEqual(f(none, trainers.Closest("bank")),
                         "Nearby: nothing within a short walk; the closest is the bank.")
        self.assertEqual(f(none, trainers.Closest("auction")),
                         "Nearby: nothing within a short walk; the closest is the auction house.")
        self.assertEqual(f(none, trainers.Closest("auction", True)),
                         f"Nearby: nothing within a short walk; the closest is the {self.NEUTRAL}.")

    def test_nothing_near_and_nothing_in_the_zone_keeps_todays_text(self):
        self.assertEqual(trainer_text.services_text(Services(False, False, False), None),
                         "Nearby: none (no bank, auction house or mailbox).")

    def test_the_closest_is_ignored_when_something_is_near(self):
        self.assertEqual(trainer_text.services_text(Services(False, False, True), trainers.Closest("bank")),
                         "Nearby: mailbox; no bank or auction house.")

    def test_a_row_with_nothing_near_names_the_closest_service(self):
        t = Trainer(1, "Lone Smith", BS, "Master", "AH", 33, (30.0, 70.0), True)
        npcs = trainers.parse_npc_rows(_npc_text(
            "[2] = {'Bank',1,1,1,1,0,{[33]={{60,70}}},nil,33,nil,nil,12,\"A\",\"Banker\",256},",
            "[3] = {'Auc',1,1,1,1,0,{[33]={{30,45}}},nil,33,nil,nil,12,\"AH\",\"Auctioneer\",4097},"))
        data = trainers.TrainerData([t], npcs, [], {33: "Somewhere"})
        text = trainer_text.remote_stop(trainer_text.TrainerInfo("alliance", data), BS, 300).text
        self.assertEqual(text, "Lone Smith, Somewhere (30.0, 70.0). Nearby: nothing within a short walk; "
                               f"the closest is the {self.NEUTRAL}.")
        self.assertNotRegex(text, r"\d+ (map|yards|units)")  # no distances

    def test_a_row_with_nothing_in_the_zone_keeps_todays_text(self):
        self.assertEqual(self.lone(33).text, "Lone Smith, Somewhere (30.0, 70.0). "
                                             "Nearby: none (no bank, auction house or mailbox).")

    def test_remote_stop_several_trainers(self):
        stop = trainer_text.remote_stop(self.info("alliance"), BS, 225)
        self.assertEqual(stop.text, "Thessa Hammerlow, Stormwind City (60.5, 40.2). "
                                    "Or Wandering Smith, Ironforge (20.0, 20.0).")

    def lone(self, zone, faction="alliance", sides="AH", confirmed=True, rows=None, mailboxes=()):
        t = Trainer(1, "Lone Smith", BS, "Master", sides, zone, (30.0, 70.0), confirmed)
        data = trainers.TrainerData([t], rows or {}, list(mailboxes), {zone: "Somewhere"})
        return trainer_text.remote_stop(trainer_text.TrainerInfo(faction, data), BS, 300)

    def test_capital_trainer_has_no_nearby_line(self):
        self.assertEqual(self.lone(1519).text, "Lone Smith, Somewhere (30.0, 70.0).")
        self.assertNotIn("Nearby", self.lone(1637, faction="horde").text)

    def test_trainer_outside_a_capital_gets_nearby(self):
        self.assertEqual(self.lone(33, mailboxes=[(33, 30.5, 70)]).text,
                         "Lone Smith, Somewhere (30.0, 70.0). Nearby: mailbox; no bank or auction house.")

    def test_trainer_in_the_other_factions_capital_still_gets_nearby(self):
        text = self.lone(1637, faction="alliance").text  # Orgrimmar is not an Alliance capital
        self.assertEqual(text, "Lone Smith, Somewhere (30.0, 70.0). Nearby: none (no bank, auction house or mailbox).")
        self.assertIn("Nearby", self.lone(1519, faction="horde").text)

    def test_unconfirmed_trainers_are_named_only_when_no_confirmed_one_exists(self):
        sure, odd = Trainer(1, "Sure Smith", BS, "Master", "AH", 33, (1, 1), True), \
            Trainer(2, "Odd Smith", BS, "Master", "AH", 33, (2, 2), False)
        mk = lambda ts: trainer_text.TrainerInfo("alliance", trainers.TrainerData(ts, {}, [], {33: "Somewhere"}))
        both = trainer_text.remote_stop(mk([odd, sure]), BS, 300).text
        self.assertIn("Sure Smith, Somewhere", both)
        self.assertNotIn("Odd Smith", both)
        only = trainer_text.remote_stop(mk([odd]), BS, 300).text
        self.assertTrue(only.startswith("Odd Smith (title unconfirmed in the data), Somewhere (2.0, 2.0)."), only)

    def test_capital_examples_prefer_confirmed_titles(self):
        ts = [Trainer(1, "Odd Smith", BS, "Expert", "A", 1519, (1, 1), False),
              Trainer(2, "Sure Smith", BS, "Expert", "A", 1537, (1, 1), True)]
        data = trainers.TrainerData(ts, {}, [], {1519: "Stormwind City", 1537: "Ironforge"})
        info = trainer_text.TrainerInfo("alliance", data)
        self.assertIn("(for example Sure Smith, Ironforge)", trainer_text.city_row(info, BS, 150))
        data.trainers.pop()
        self.assertIn("(for example Odd Smith (title unconfirmed in the data), Stormwind City)",
                      trainer_text.city_row(info, BS, 150))

    def test_instance_trainer_says_inside(self):
        self.assertEqual(trainer_text.remote_stop(self.info("horde"), ENCH, 300).text,
                         "Zarn Runeweaver, inside Uldaman.")
        self.assertEqual(trainer_text.remote_stop(self.info("alliance"), ALCH, 300).text,
                         "Dorn Deepdelver, inside Hollow Depths (Misty Vale).")

    def test_no_trainer_for_the_faction(self):
        stop = trainer_text.remote_stop(self.info("horde"), BS, 225)
        self.assertEqual((stop.text, stop.found),
                         ("the planner has no Artisan Blacksmith trainer for your faction in its data.", False))

    def test_city_row_names_capital_trainers(self):
        text = trainer_text.city_row(self.info("horde"), BS, 150)
        self.assertEqual(text, "Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                               "(for example Grom Anvilhand, Orgrimmar).")

    def test_city_row_with_no_capital_trainer_names_the_others_plainly(self):
        data = trainers.TrainerData([Trainer(1, "Far Smith", BS, "Expert", "A", 33, (1, 1), True),
                                     Trainer(2, "Odd Smith", BS, "Expert", "A", 34, (1, 1), False)],
                                    {}, [], {33: "Somewhere", 34: "Elsewhere"})
        text = trainer_text.city_row(trainer_text.TrainerInfo("alliance", data), BS, 150)
        self.assertEqual(text, "Train Blacksmithing to 150 at Far Smith, Somewhere "
                               "(no Expert Blacksmith in a capital in the data).")
        self.assertNotIn("in a capital.", text)
        self.assertNotIn("Odd Smith", text)

    def test_city_row_names_at_most_two(self):
        ts = [Trainer(i, f"Smith {i}", BS, "Expert", "A", z, (1, 1), True)
              for i, z in ((1, 1519), (2, 1537), (3, 1657))]
        data = trainers.TrainerData(ts, {}, [], {1519: "Stormwind City", 1537: "Ironforge", 1657: "Darnassus"})
        text = trainer_text.city_row(trainer_text.TrainerInfo("alliance", data), BS, 150)
        self.assertEqual(text, "Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                               "(for example Smith 1, Stormwind City or Smith 2, Ironforge).")

    def test_add_note_joins_into_one_parenthesis(self):
        note = trainer_text.listed_note(35)
        self.assertEqual(trainer_text.add_note("Learn X (trainer 1s 0c)", note),
                         "Learn X (trainer 1s 0c; listed from 35 in the Forever data: "
                         "if the trainer offers it then, you can start it earlier)")
        self.assertEqual(trainer_text.add_note("Learn X", note), "Learn X" + note)
        self.assertEqual(trainer_text.add_note("Learn X (a)", ""), "Learn X (a)")

    def test_city_row_no_trainer_for_faction(self):
        self.assertEqual(trainer_text.city_row(self.info("alliance"), BS, 150),
                         "Train Blacksmithing to 150: the planner has no Expert Blacksmith trainer for your faction in its data.")

    def test_no_faction_or_no_data_names_nothing(self):
        self.assertIsNone(trainer_text.remote_stop(trainer_text.TrainerInfo("", self.data), BS, 300))
        self.assertIsNone(trainer_text.remote_stop(None, BS, 300))
        self.assertIsNone(trainer_text.city_row(trainer_text.TrainerInfo("alliance", None), BS, 150))
        self.assertIsNone(trainer_text.remote_stop(self.info("alliance"), BS, 100))  # no such rank


class NoteRowTests(unittest.TestCase):
    """What the notes from play add to a trainer row (Artisan and Master)."""
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_data()

    def stop(self, note, level=None, npc=90001, faction="alliance", profession=BS, cap=300):
        notes = Notes({npc: note} if note is not None else {}, {})
        info = trainer_text.TrainerInfo(faction, self.data, notes)
        return trainer_text.remote_stop(info, profession, cap, level).text

    PLACE = "Brakka Ironfold, Stranglethorn Vale (30.0, 70.0). Nearby: bank, " \
            "neutral AH (its own prices and a higher deposit), mailbox."

    def test_reach_and_flight_path(self):
        self.assertEqual(self.stop(TrainerNote(reach_level=35, flight_path=True), level=40),
                         self.PLACE + " Easy to reach from about level 35, with a flight path for repeat visits.")

    def test_reach_alone(self):
        self.assertEqual(self.stop(TrainerNote(reach_level=20), level=20),
                         self.PLACE + " Easy to reach from about level 20.")

    def test_flight_path_alone(self):
        self.assertEqual(self.stop(TrainerNote(flight_path=True), level=20),
                         self.PLACE + " With a flight path for repeat visits.")

    def test_note_alone(self):
        self.assertEqual(self.stop(TrainerNote(note="A tip."), level=20), self.PLACE + " A tip.")

    def test_all_three_in_order(self):
        self.assertEqual(self.stop(TrainerNote(reach_level=20, flight_path=True, note="A tip."), level=25),
                         self.PLACE + " Easy to reach from about level 20, with a flight path for repeat visits. "
                                      "A tip.")

    def test_below_the_reach_level_says_so(self):
        self.assertEqual(self.stop(TrainerNote(reach_level=35, flight_path=True, note="A tip."), level=30),
                         self.PLACE + " Easy to reach from about level 35, with a flight path for repeat visits "
                                      "(you're level 30: the first trip is harder). A tip.")
        self.assertEqual(self.stop(TrainerNote(reach_level=35), level=1),
                         self.PLACE + " Easy to reach from about level 35 (you're level 1: the first trip is harder).")

    def test_at_the_reach_level_it_is_not_harder(self):
        self.assertNotIn("harder", self.stop(TrainerNote(reach_level=35), level=35))

    def test_below_level_without_a_reach_level_says_nothing(self):
        self.assertNotIn("you're level", self.stop(TrainerNote(flight_path=True, note="A tip."), level=1))

    def test_unknown_level_says_nothing_about_it(self):
        self.assertNotIn("you're level", self.stop(TrainerNote(reach_level=35), level=None))

    def test_a_trainer_without_notes_is_unchanged(self):
        plain = self.stop(None, level=30)
        self.assertEqual(plain, self.PLACE)
        self.assertEqual(self.stop(TrainerNote(), level=30), plain)
        self.assertEqual(self.stop(None, level=30, npc=90001),
                         trainer_text.remote_stop(trainer_text.TrainerInfo("alliance", self.data), BS, 300).text)

    def test_notes_of_another_trainer_do_not_leak(self):
        self.assertEqual(self.stop(TrainerNote(reach_level=35), npc=12345, level=1), self.PLACE)

    def test_instance_trainer_group_and_solo(self):
        note = TrainerNote(group_level=37, solo_level=52, note="A group can go earlier.")
        self.assertEqual(self.stop(note, level=45, npc=90006, faction="horde", profession=ENCH),
                         "Zarn Runeweaver, inside Uldaman. Go with a group from about level 37, "
                         "solo from about level 52. A group can go earlier.")

    def test_instance_trainer_below_the_group_level(self):
        note = TrainerNote(group_level=37, solo_level=52, note="A group can go earlier.")
        self.assertEqual(self.stop(note, level=30, npc=90006, faction="horde", profession=ENCH),
                         "Zarn Runeweaver, inside Uldaman. Go with a group from about level 37, "
                         "solo from about level 52 (you're level 30). A group can go earlier.")
        # at the group level, and between group and solo, nothing is added
        for level in (37, 40, 52, 60):
            self.assertNotIn("you're level",
                             self.stop(note, level=level, npc=90006, faction="horde", profession=ENCH), level)

    def test_each_trainer_named_gets_its_own_notes(self):
        notes = Notes({90002: TrainerNote(note="One."), 90017: TrainerNote(note="Two.")}, {})
        info = trainer_text.TrainerInfo("alliance", self.data, notes)
        self.assertEqual(trainer_text.remote_stop(info, BS, 225, 60).text,
                         "Thessa Hammerlow, Stormwind City (60.5, 40.2). One. "
                         "Or Wandering Smith, Ironforge (20.0, 20.0). Two.")

    def test_the_notes_say_nothing_about_services_known(self):
        info = trainer_text.TrainerInfo("alliance", self.data, Notes({90001: TrainerNote(note="A tip.")}, {}))
        self.assertTrue(trainer_text.remote_stop(info, BS, 300, 60).services_known)


class CityTipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture_data()

    def row(self, cities, faction="alliance", profession=BS, cap=150, data=None):
        info = trainer_text.TrainerInfo(faction, data or self.data, Notes({}, cities))
        return trainer_text.city_row(info, profession, cap)

    def test_the_tip_follows_the_row(self):
        got = self.row({1519: "A tip."}, profession=TAILOR, cap=75)
        self.assertEqual(got, "Train Tailoring to 75 at any Journeyman Tailor in a capital "
                              "(for example Olla Stitchwell, Stormwind City). A tip.")

    def test_a_city_without_a_tip_is_unchanged(self):
        plain = trainer_text.city_row(trainer_text.TrainerInfo("horde", self.data), BS, 150)
        self.assertEqual(self.row({1519: "A tip."}, faction="horde"), plain)
        self.assertNotIn("A tip", plain)

    def test_each_tip_once_in_example_order(self):
        ts = [Trainer(i, f"Smith {i}", BS, "Expert", "A", z, (1, 1), True)
              for i, z in ((1, 1519), (2, 1537), (3, 1519))]
        data = trainers.TrainerData(ts, {}, [], {1519: "Stormwind City", 1537: "Ironforge"})
        got = self.row({1519: "Stormwind tip.", 1537: "Ironforge tip."}, data=data)
        self.assertEqual(got, "Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                              "(for example Smith 1, Stormwind City or Smith 2, Ironforge). "
                              "Stormwind tip. Ironforge tip.")
        data = trainers.TrainerData([ts[0], ts[2]], {}, [], {1519: "Stormwind City"})
        self.assertEqual(self.row({1519: "Stormwind tip."}, data=data).count("Stormwind tip."), 1)

    def test_a_tip_for_a_city_not_named_is_left_out(self):
        ts = [Trainer(i, f"Smith {i}", BS, "Expert", "A", z, (1, 1), True)
              for i, z in ((1, 1519), (2, 1537), (3, 1657))]
        data = trainers.TrainerData(ts, {}, [], {1519: "Stormwind City", 1537: "Ironforge", 1657: "Darnassus"})
        self.assertNotIn("Darnassus tip", self.row({1657: "Darnassus tip."}, data=data))

    def test_a_row_without_a_capital_trainer_has_no_tip(self):
        data = trainers.TrainerData([Trainer(1, "Far Smith", BS, "Expert", "A", 33, (1, 1), True)],
                                    {}, [], {33: "Somewhere"})
        self.assertNotIn("tip", self.row({33: "A tip."}, data=data))

    def test_no_notes_is_todays_row(self):
        info = trainer_text.TrainerInfo("horde", self.data)
        self.assertEqual(trainer_text.city_row(info, BS, 150),
                         "Train Blacksmithing to 150 at any Expert Blacksmith in a capital "
                         "(for example Grom Anvilhand, Orgrimmar).")


class ShippedNotesTests(unittest.TestCase):
    def test_every_city_tip_is_for_a_capital(self):
        for zone in trainer_notes.load_notes().cities:
            self.assertIn(zone, trainers.CAPITALS["alliance"] + trainers.CAPITALS["horde"])


REAL = settings.paths(settings.home({})).gamedata  # the player's real cache (read only), not the test home
HAVE_REAL = all((REAL / n).exists() for n in gamedata.TRAINER_FILES)


@unittest.skipUnless(HAVE_REAL, "real trainer data not downloaded")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = trainers.load_trainer_data(REAL)
        cls.by_id = {t.npc_id: t for t in cls.data.trainers}

    def test_every_noted_npc_is_an_artisan_or_master_trainer(self):
        for npc in trainer_notes.load_notes().trainers:
            self.assertIn(npc, self.by_id, npc)
            self.assertIn(self.by_id[npc].rank, ("Artisan", "Master"), npc)

    def test_booty_bay_auctioneers_serve_both_factions(self):
        # Brikk Keencraft, Master Blacksmith in Booty Bay
        near = trainers.nearby(self.by_id[2836], self.data.npc_rows, self.data.mailboxes, trainers.NEARBY_RADIUS)
        self.assertTrue(near.auction and near.neutral_auction)
        info = trainer_text.TrainerInfo("alliance", self.data)
        self.assertIn("neutral AH (its own prices and a higher deposit)", trainer_text.remote_stop(info, BS, 300).text)

    def test_pinned_tailoring_master_rank_has_a_level(self):
        gd = gamedata.load_gamedata(REAL, professions=[TAILOR])
        self.assertEqual(gd.trainer_ranks[TAILOR][-1].cap, 300)
        self.assertEqual(gd.trainer_ranks[TAILOR][-1].level, 35)


class LoadInfoTests(unittest.TestCase):
    def folder(self, d):
        for p in FIX.iterdir():
            (Path(d) / p.name).write_bytes(p.read_bytes())
        return Path(d)

    def test_loads_after_fetching_only_the_trainer_files(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(gamedata, "fetch_all") as fetch:
            info, note = trainer_text.load_info(self.folder(d), "horde")
        fetch.assert_called_once_with(dest=Path(d), only=gamedata.TRAINER_FILES)
        self.assertEqual((info.faction, note), ("horde", ""))
        self.assertTrue(info.data.trainers)

    def test_loads_the_shipped_notes(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(gamedata, "fetch_all"):
            info, _note = trainer_text.load_info(self.folder(d), "horde")
        self.assertEqual(info.notes, trainer_notes.load_notes())

    def test_unusable_notes_are_a_note_and_the_trainers_are_still_named(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(gamedata, "fetch_all"), \
                unittest.mock.patch.object(trainer_notes, "load_notes", side_effect=ValueError("trainers.1 is wrong")):
            info, note = trainer_text.load_info(self.folder(d), "horde")
        self.assertIsNone(info.notes)
        self.assertTrue(info.data.trainers)
        self.assertEqual(note, "Trainer notes are left out of this guide: trainers.1 is wrong.")

    def test_no_faction_downloads_nothing(self):
        with unittest.mock.patch.object(gamedata, "fetch_all") as fetch:
            self.assertEqual(trainer_text.load_info(Path("x"), ""), (None, ""))
        fetch.assert_not_called()

    def test_damaged_file_gives_a_note_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(gamedata, "fetch_all"):
            (self.folder(d) / "foreverNpcDB.lua").write_text("QuestieDB.npcData = [[return {", encoding="utf-8")
            info, note = trainer_text.load_info(Path(d), "alliance")
        self.assertIsNone(info)
        self.assertIn("Trainer names are left out", note)
        self.assertIn("foreverNpcDB.lua is damaged", note)

    def test_missing_files_and_no_network_give_a_note(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(
                gamedata, "fetch_all", side_effect=urllib.error.URLError("offline")):
            info, note = trainer_text.load_info(Path(d), "alliance")
        self.assertIsNone(info)
        self.assertIn("Trainer names are left out", note)
        self.assertIn("offline", note)
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(gamedata, "fetch_all"):
            info, note = trainer_text.load_info(Path(d), "alliance")
        self.assertIsNone(info)
        self.assertIn("missing", note)


class TripKindTests(unittest.TestCase):
    def plan(self):
        from yap_forever.planner import Plan
        return Plan(ranks=[(BS, 60, 150, 450), (BS, 200, 225, 4500), (BS, 275, 300, 9000)])

    def test_expert_rank_is_not_a_trip(self):
        from yap_forever.trips import trips
        from tests import toy
        got = trips(self.plan(), toy.gamedata([]))
        self.assertEqual([(t.kind, t.skill, t.cap) for t in got], [("rank", 200, 225), ("rank", 275, 300)])

    def test_city_ranks_are_the_ranks_below_the_remote_ones(self):
        from yap_forever.trips import city_ranks
        got = city_ranks(self.plan())
        self.assertEqual([(t.kind, t.skill, t.cap, t.profession) for t in got], [("city", 60, 150, BS)])


class ListedNoteTests(unittest.TestCase):
    def test_listed_note_names_the_forever_skill(self):
        self.assertEqual(trainer_text.listed_note(180),
                         " (listed from 180 in the Forever data: if the trainer offers it then, you can start it earlier)")


if __name__ == "__main__":
    unittest.main()
