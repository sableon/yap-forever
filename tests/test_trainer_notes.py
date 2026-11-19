"""trainer_notes.toml: facts from play about each Artisan and Master trainer, and how the loader checks them."""
import tempfile
import unittest
from pathlib import Path

from yap_forever import trainer_notes
from yap_forever.trainer_notes import Notes, TrainerNote


def load(text: str) -> Notes:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "trainer_notes.toml"
        path.write_text(text, encoding="utf-8")
        return trainer_notes.load_notes(path)


def message(text: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "trainer_notes.toml"
        path.write_text(text, encoding="utf-8")
        with unittest.TestCase().assertRaises(ValueError) as cm:
            trainer_notes.load_notes(path)
    return str(cm.exception)


class LoadTests(unittest.TestCase):
    def test_a_good_file(self):
        got = load('''
[trainers.100]
reach_level = 35
flight_path = true
note = "A short sentence."

[trainers.101]
group_level = 37
solo_level = 52

[trainers.102]
flight_path = false

[trainers.103]
nearby = ["mail", "bank", "auction"]

[cities]
1657 = "A tip."

[cities.1519]
tip = "Another tip."
professions = ["alchemy", "engineering"]
''')
        self.assertEqual(got.trainers[100], TrainerNote(reach_level=35, flight_path=True, note="A short sentence."))
        self.assertEqual(got.trainers[101], TrainerNote(group_level=37, solo_level=52))
        self.assertEqual(got.trainers[102], TrainerNote())
        self.assertEqual(got.trainers[103], TrainerNote(nearby=("mail", "bank", "auction")))
        self.assertEqual(got.cities, {1657: "A tip.", 1519: "Another tip."})
        self.assertEqual(got.city_professions, {1519: frozenset({171, 202})})

    def test_an_empty_file_is_no_notes(self):
        self.assertEqual(load(""), Notes({}, {}))

    def test_a_missing_file_is_a_message(self):
        with self.assertRaises(ValueError) as cm:
            trainer_notes.load_notes(Path("/nonexistent/trainer_notes.toml"))
        self.assertIn("trainer_notes.toml", str(cm.exception))

    def test_toml_that_does_not_parse_is_a_message(self):
        self.assertIn("not valid TOML", message("[trainers.1\nreach_level = 3"))

    def test_a_file_that_is_not_utf8_is_a_message(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "n.toml"
            path.write_bytes(b'[cities]\n1 = "\xff\xfe"\n')
            with self.assertRaises(ValueError):
                trainer_notes.load_notes(path)

    def test_unknown_keys_are_refused(self):
        self.assertIn("unknown", message("[trainers.1]\nreach = 3\n"))
        self.assertIn("unknown", message("[extra]\nx = 1\n"))

    def test_levels_must_be_whole_numbers_from_1_to_60(self):
        for bad in ("0", "-5", "61", "35.5", '"35"', "true"):
            self.assertIn("reach_level", message(f"[trainers.1]\nreach_level = {bad}\n"), bad)
        self.assertIn("group_level", message("[trainers.1]\ngroup_level = 0\nsolo_level = 52\n"))
        self.assertIn("solo_level", message("[trainers.1]\ngroup_level = 37\nsolo_level = 61\n"))
        for good in ("1", "60"):
            load(f"[trainers.1]\nreach_level = {good}\n")

    def test_flight_path_must_be_a_bool(self):
        for bad in ("1", '"yes"'):
            self.assertIn("flight_path", message(f"[trainers.1]\nflight_path = {bad}\n"), bad)

    def test_note_must_be_a_non_empty_string(self):
        for bad in ('""', "5", '"   "'):
            self.assertIn("note", message(f"[trainers.1]\nnote = {bad}\n"), bad)

    def test_group_and_solo_come_together_and_in_order(self):
        self.assertIn("together", message("[trainers.1]\ngroup_level = 37\n"))
        self.assertIn("together", message("[trainers.1]\nsolo_level = 37\n"))
        self.assertIn("below", message("[trainers.1]\ngroup_level = 50\nsolo_level = 40\n"))

    def test_an_instance_trainer_has_no_reach_level(self):
        self.assertIn("reach_level", message("[trainers.1]\nreach_level = 30\ngroup_level = 37\nsolo_level = 52\n"))

    def test_trainer_keys_are_npc_ids(self):
        self.assertIn("NPC", message("[trainers.abc]\nreach_level = 3\n"))
        self.assertIn("NPC", message("[trainers.0]\nreach_level = 3\n"))

    def test_nearby_values_are_checked(self):
        for bad in ('"mail"', '["post"]', '["mail", "mail"]', "[1]", "[]"):
            self.assertIn("nearby", message(f"[trainers.1]\nnearby = {bad}\n"), bad)
        load('[trainers.1]\nnearby = ["bank"]\n')

    def test_city_professions_are_checked(self):
        for bad in ('"alchemy"', '["mining"]', "[]", "[171]", '["alchemy", "alchemy"]'):
            self.assertIn("professions", message(f'[cities.1519]\ntip = "t"\nprofessions = {bad}\n'), bad)
        self.assertIn("tip", message('[cities.1519]\nprofessions = ["alchemy"]\n'))
        self.assertIn("unknown", message('[cities.1519]\ntip = "t"\nextra = 1\n'))

    def test_trainers_must_be_tables_and_cities_strings(self):
        self.assertIn("trainers", message("trainers = 5\n"))
        self.assertIn("trainers.1", message("[trainers]\n1 = 5\n"))
        self.assertIn("cities", message("[cities]\n1657 = 5\n"))
        self.assertIn("cities", message('[cities]\nx = "tip"\n'))
        self.assertIn("cities", message('[cities]\n1657 = ""\n'))

    def test_the_message_is_not_the_cache_one(self):
        # a shipped file is not fixed by deleting and downloading it again
        self.assertNotIn("download", message("[trainers.1]\nreach = 3\n"))


class ShippedFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notes = trainer_notes.load_notes()

    def test_twelve_trainers_and_two_cities(self):
        self.assertEqual(sorted(self.notes.trainers),
                         sorted([7948, 1386, 2836, 3355, 11073, 11072, 11074, 8736, 11097, 11098, 11052, 2399]))
        self.assertEqual(sorted(self.notes.cities), [1519, 1657])

    def test_values_from_play(self):
        t = self.notes.trainers
        self.assertEqual(t[7948], TrainerNote(reach_level=35, flight_path=True))
        self.assertEqual(t[1386], TrainerNote(reach_level=35, flight_path=True,
                                              note="The first trip crosses three zones."))
        self.assertEqual(t[2836], TrainerNote(reach_level=20, flight_path=True,
                                              note="A safe neutral town; a long first trip for Alliance."))
        self.assertEqual(t[3355], TrainerNote(note="Far from the bank and the AH; the mailbox is closest."))
        self.assertEqual(t[11073], TrainerNote(
            group_level=37, solo_level=52,
            note="A group can go from about 35, but groups are easier to find from 37–39 and full runs from 42."))
        self.assertEqual(t[11072], TrainerNote(note="Close to Stormwind."))
        self.assertEqual(t[11074], TrainerNote(reach_level=20, flight_path=True))
        self.assertEqual(t[8736], TrainerNote(reach_level=35, flight_path=True))
        self.assertEqual(t[11097], TrainerNote(reach_level=35, flight_path=True))
        self.assertEqual(t[11098], TrainerNote(reach_level=37, flight_path=True,
                                               note="Some danger on the road the first time."))
        self.assertEqual(t[11052], TrainerNote(
            reach_level=20, nearby=("mail",), note="A safe town; a long first trip for Alliance."))
        self.assertEqual(t[2399], TrainerNote(reach_level=18, flight_path=True))

    def test_city_tips(self):
        self.assertEqual(self.notes.cities, {
            1657: "The bank and the AH are far apart.",
            1519: "The Alchemy and Engineering trainers are a long walk from the bank and the AH."})
        self.assertEqual(self.notes.city_professions, {1519: frozenset({171, 202})})  # Darnassus: every profession


if __name__ == "__main__":
    unittest.main()
