import json
import tempfile
import unittest
from pathlib import Path

from yap_forever import bnet, probe, profile
from yap_forever.bnet import Response

EXAMPLE = """region = "eu"        # eu, us, kr or tw
ruleset = 2          # 2 = Normal
faction = "alliance" # alliance or horde
[characters.Main]
favor_standing = "Neutral"
"""


def write(d: str, text: str) -> Path:
    p = Path(d) / "profile.toml"
    p.write_text(text, encoding="utf-8")
    return p


class ProfileTests(unittest.TestCase):
    def test_load_profile_example(self):
        with tempfile.TemporaryDirectory() as d:
            prof = profile.load_profile(write(d, EXAMPLE))
        self.assertEqual((prof.region, prof.ruleset, prof.faction), ("eu", 2, "alliance"))
        self.assertEqual(prof.characters, {"Main": profile.Character("Main", "Neutral")})

    def test_load_profile_bad_faction(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as cm:
                profile.load_profile(write(d, EXAMPLE.replace('"alliance"', '"orc"')))
        self.assertIn("faction", str(cm.exception))

    def test_load_profile_bad_standing(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as cm:
                profile.load_profile(write(d, EXAMPLE.replace('"Neutral"', '"Best friends"')))
        self.assertIn("favor_standing", str(cm.exception))

    def test_talent_keys_default_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            prof = profile.load_profile(write(d, EXAMPLE))
        self.assertEqual(prof.overtime_reading, "relative")
        self.assertEqual(prof.characters["Main"].working_overtime, 0)
        self.assertFalse(prof.characters["Main"].dedicated_study)

    def test_talent_keys_parsed(self):
        text = EXAMPLE + "working_overtime = 3\ndedicated_study = true\n"
        with tempfile.TemporaryDirectory() as d:
            prof = profile.load_profile(write(d, 'working_overtime_reading = "points"\n' + text))
        self.assertEqual(prof.overtime_reading, "points")
        self.assertEqual(prof.characters["Main"], profile.Character("Main", "Neutral", 3, True))

    def test_working_overtime_out_of_range(self):
        for bad in ("6", "-1"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError) as cm:
                    profile.load_profile(write(d, EXAMPLE + f"working_overtime = {bad}\n"))
                self.assertIn("characters.Main.working_overtime", str(cm.exception))
                self.assertIn("0-5", str(cm.exception))

    def test_working_overtime_not_a_whole_number(self):
        for bad in ('"3"', "2.5", "true"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError) as cm:
                    profile.load_profile(write(d, EXAMPLE + f"working_overtime = {bad}\n"))
                self.assertIn("characters.Main.working_overtime", str(cm.exception))

    def test_dedicated_study_must_be_true_or_false(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as cm:
                profile.load_profile(write(d, EXAMPLE + 'dedicated_study = "yes"\n'))
        self.assertIn("characters.Main.dedicated_study", str(cm.exception))

    def test_working_overtime_reading_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as cm:
                profile.load_profile(write(d, 'working_overtime_reading = "both"\n' + EXAMPLE))
        msg = str(cm.exception)
        self.assertIn("working_overtime_reading", msg)
        self.assertIn("relative", msg)
        self.assertIn("points", msg)

    def test_load_profile_missing_says_init(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError) as cm:
                profile.load_profile(Path(d) / "profile.toml")
        self.assertIn("init", str(cm.exception))

    def test_house_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "house.json"
            profile.save_house(f, 7, "us", 2)
            self.assertEqual(profile.load_house(f), 7)
            self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["region"], "us")

    def test_load_house_missing_says_probe(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError) as cm:
                profile.load_house(Path(d) / "house.json")
        self.assertIn("probe", str(cm.exception))


class ApiShapeTests(unittest.TestCase):
    def test_namespace_us(self):
        self.assertEqual(bnet.namespace("us"), "dynamic-forever-us")

    def test_house_path_ruleset(self):
        self.assertEqual(bnet.house_path(5, 3, True), "/data/wow/ruleset/3/auctions/5/commodities")

    def test_index_houses(self):
        self.assertEqual(bnet.index_houses({"auctions": [{"id": 9}, {"id": 2}]}), [2, 9])


class FakeClient:
    """Answers the auctions index and per-house listings from dicts."""

    def __init__(self, houses: list[int], marker_in: list[int], item=2589, buyout=71313):
        self.houses, self.marker_in, self.item, self.buyout = houses, marker_in, item, buyout
        self.paths = []

    def get(self, path, if_modified_since=None):
        self.paths.append(path)
        if path.endswith("/auctions/index"):
            return Response(200, {"auctions": [{"id": h} for h in self.houses]}, None)
        house = int(path.split("/auctions/")[1].split("/")[0])
        if path.endswith("/commodities"):
            return Response(200, {"auctions": []}, None)
        auctions = ([{"item": {"id": self.item}, "buyout": self.buyout, "quantity": 1}]
                    if house in self.marker_in else [])
        return Response(200, {"auctions": auctions}, None)


class ProbeTests(unittest.TestCase):
    def test_probe_scans_index_houses(self):
        client = FakeClient([3, 7, 9], [7])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "house.json"
            code = probe.run(client, "eu", 2, 2589, 71313, f)
            self.assertEqual(code, 0)
            self.assertEqual(profile.load_house(f), 7)
        scanned = {p for p in client.paths if not p.endswith("index")}
        self.assertEqual(len(scanned), 6)  # 3 houses x (regular + commodities)

    def test_ambiguous_marker_keeps_house_file(self):
        client = FakeClient([3, 7, 9], [3, 7])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "house.json"
            f.write_text('{"house": 4242}', encoding="utf-8")
            before = f.read_bytes()
            code = probe.run(client, "eu", 2, 2589, 71313, f)
            self.assertEqual(code, 1)
            self.assertEqual(f.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
