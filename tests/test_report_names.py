import hashlib
import unittest

from yap_forever.profile import report_name


def digest(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


class ReportNameTests(unittest.TestCase):
    def test_full_name_casefolded_with_dashes(self):
        self.assertEqual(report_name("Testy Example"), "testy-example")

    def test_runs_of_whitespace_become_one_dash(self):
        self.assertEqual(report_name("Testy \t  Example"), "testy-example")

    def test_names_sharing_the_first_word_differ(self):
        names = ["Testy Example", "Testy Sample"]
        self.assertEqual([report_name(n, names) for n in names], ["testy-example", "testy-sample"])

    def test_names_sharing_the_second_word_differ(self):
        names = ["Testy Example", "Nobby Example"]
        self.assertEqual([report_name(n, names) for n in names], ["testy-example", "nobby-example"])

    def test_accented_letters_are_kept(self):
        self.assertEqual(report_name("Élise Brightforge"), "élise-brightforge")

    def test_characters_windows_refuses_are_dropped(self):
        self.assertEqual(report_name('Te<s>t:y "Ex/am\\ple|?*'), "testy-example")
        self.assertEqual(report_name("Testy\x01 Example"), "testy-example")
        self.assertEqual(report_name("Test\x07y Example"), "testy-example")

    def test_only_refused_characters_get_a_hash(self):
        name = '<>:"/\\|?*'
        self.assertEqual(report_name(name), f"-{digest(name)}")

    def test_hash_is_of_the_full_name_not_the_casefolded_one(self):
        name = "<Ä>"
        self.assertEqual(report_name(name, [name, "Ä"]), f"ä-{digest(name)}")
        self.assertNotEqual(digest(name), digest(name.casefold()))

    def test_profile_names_giving_the_same_name_each_get_a_hash(self):
        names = ["Testy Example", "testy  EXAMPLE", "Nobby Example"]
        got = [report_name(n, names) for n in names]
        self.assertEqual(got[0], f"testy-example-{digest(names[0])}")
        self.assertEqual(got[1], f"testy-example-{digest(names[1])}")
        self.assertNotEqual(got[0], got[1])
        self.assertEqual(got[2], "nobby-example")

    def test_same_result_whatever_the_order_of_the_profile(self):
        names = ["Testy Example", "TESTY  Example"]
        self.assertEqual(report_name(names[0], names), report_name(names[0], names[::-1]))

    def test_the_name_itself_in_the_profile_is_not_a_collision(self):
        self.assertEqual(report_name("Testy Example", ["Testy Example"]), "testy-example")

    def test_composed_and_decomposed_spellings_are_one_name(self):
        composed, decomposed = "Zo\u00e9 Example", "Zoe\u0301 Example"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(report_name(composed), report_name(decomposed))
        names = [composed, decomposed]
        got = [report_name(n, names) for n in names]
        self.assertEqual(got[0], f"zo\u00e9-example-{digest(composed)}")
        self.assertEqual(got[1], f"zo\u00e9-example-{digest(decomposed)}")
        self.assertNotEqual(got[0], got[1])

    def test_hash_is_utf8_sha1_first_8_hex(self):
        self.assertEqual(digest("Élise Brightforge"),
                         hashlib.sha1("Élise Brightforge".encode()).hexdigest()[:8])
        self.assertRegex(report_name("<>", ["<>"]), r"^-[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
