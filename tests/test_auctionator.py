import contextlib
import datetime
import io
import struct
import tempfile
import unittest
from pathlib import Path

from yap_forever import auctionator, cli, settings
from yap_forever.auctionator import cbor_decode, lua_string_at, realms, load_auctionator
from yap_forever.prices import Market

EPOCH = datetime.date(2020, 1, 1)
NEWEST = (datetime.date(2026, 11, 18) - EPOCH).days  # a made-up scan day, 2026-11-18


# --- a tiny CBOR encoder, for fixtures only -----------------------------------------------------

def _head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([major << 5 | n])
    if n < 1 << 8:
        return bytes([major << 5 | 24, n])
    if n < 1 << 16:
        return bytes([major << 5 | 25]) + struct.pack(">H", n)
    if n < 1 << 32:
        return bytes([major << 5 | 26]) + struct.pack(">I", n)
    return bytes([major << 5 | 27]) + struct.pack(">Q", n)


def enc(x) -> bytes:
    """Auctionator's shape: ints, byte strings (str), arrays, maps."""
    if isinstance(x, bool):
        return bytes([0xF5 if x else 0xF4])
    if x is None:
        return b"\xf6"
    if isinstance(x, int):
        return _head(0, x) if x >= 0 else _head(1, -1 - x)
    if isinstance(x, float):
        return b"\xfb" + struct.pack(">d", x)
    if isinstance(x, str):
        return _head(2, len(x.encode("latin-1"))) + x.encode("latin-1")
    if isinstance(x, (list, tuple)):
        return _head(4, len(x)) + b"".join(enc(i) for i in x)
    if isinstance(x, dict):
        return _head(5, len(x)) + b"".join(enc(k) + enc(v) for k, v in x.items())
    raise TypeError(x)


def lua_escape(data: bytes) -> bytes:
    """Escape as WoW does: \\r \\n \\\\ \\" by letter, other control bytes and some high bytes as \\ddd."""
    out = bytearray()
    for i, b in enumerate(data):
        if b == 0x0D:
            out += b"\\r"
        elif b == 0x0A:
            out += b"\\n"
        elif b == 0x5C:
            out += b"\\\\"
        elif b == 0x22:
            out += b'\\"'
        elif b < 0x20 or (b >= 0x80 and i % 2):
            out += b"\\%03d" % b
        else:
            out.append(b)  # printable, or a raw high byte (the real file is not valid UTF-8)
    return bytes(out)


def item(m, a, h=None, l=None) -> dict:
    return {"m": m, "h": {str(k): v for k, v in (h or {}).items()} or [],
            "l": {str(k): v for k, v in (l or {}).items()} or [],
            "a": {str(k): v for k, v in a.items()}}


def realm_data() -> dict:
    return {
        "2840": item(1250, {NEWEST - 1: 3, NEWEST - 3: 9}, h={NEWEST: 5}),  # latest a day is NEWEST - 1
        "2841": item(300, {NEWEST - 3: 4}),  # exactly 3 days before: kept; l is an empty array
        "2842": item(200, {NEWEST: 2}, l={NEWEST: 150}),  # m = 200 puts a byte >= 0x80 in the payload
        "2843": item(77, {NEWEST - 4: 5}),  # 4 days before: dropped
        "2844": item(500, {NEWEST - 1: 0}),  # nothing available: dropped
        "13": item(13, {NEWEST: 10}),  # m = 13 (CR), quantity 10 (LF)
        "14": item(34, {NEWEST: 92}),  # m = 34 ("), quantity 92 (\)
        "g:7": {"x": 1},  # not an item
        "version": 2,
    }


def payload(data: dict | None = None) -> bytes:
    return enc(data if data is not None else realm_data())


def lua_file(realm_payloads: dict[str, bytes]) -> bytes:
    lines = [b"", b"AUCTIONATOR_PRICE_DATABASE = {", b'\t["__dbversion"] = 8,']
    for key, p in realm_payloads.items():
        lines.append(b'\t["' + key.encode() + b'"] = "' + lua_escape(p) + b'",')
    lines += [b"}", b"AUCTIONATOR_POSTING_HISTORY = {",
              b'\t["TestRealm"] = "decoy",', b"}", b""]
    return b"\r\n".join(lines)


def table(*entries: bytes) -> bytes:
    return b"X = 1\r\nAUCTIONATOR_PRICE_DATABASE = {\r\n" + b"".join(entries) + b"}\r\n"


class LuaStringTests(unittest.TestCase):
    def test_every_escape_kind(self):
        raw = table(b'["k"] = "a\\r\\n\\\\\\"\\\'\\t\\a\\b\\f\\v|\\0|\\65\\066\\0011|\\200",\r\n')
        self.assertEqual(lua_string_at(raw, b"k"),
                         b'a\r\n\\"\'\t\a\b\f\v|\x00|AB\x011|\xc8')

    def test_backslash_newline_is_one_newline(self):
        raw = table(b'["k"] = "a\\\nb\\\r\nc\\\rd"')
        self.assertEqual(lua_string_at(raw, b"k"), b"a\nb\nc\nd")

    def test_raw_high_bytes_pass_through(self):
        self.assertEqual(lua_string_at(table(b'["k"] = "\xff\xfe"'), b"k"), b"\xff\xfe")

    def test_decimal_escape_over_255_is_an_error(self):
        with self.assertRaises(ValueError):
            lua_string_at(table(b'["k"] = "\\256"'), b"k")

    def test_unknown_escape_is_an_error(self):
        with self.assertRaises(ValueError):
            lua_string_at(table(b'["k"] = "\\q"'), b"k")

    def test_missing_key_or_unterminated_string(self):
        with self.assertRaises(ValueError):
            lua_string_at(table(b'["k"] = "abc"'), b"other")
        with self.assertRaises(ValueError):
            lua_string_at(b'AUCTIONATOR_PRICE_DATABASE = {["k"] = "abc', b"k")


class CborTests(unittest.TestCase):
    def test_roundtrip_of_what_auctionator_stores(self):
        data = realm_data()
        self.assertEqual(cbor_decode(payload(data)), data)

    def test_integer_widths_and_negative(self):
        for n in (0, 23, 24, 255, 256, 65535, 65536, 2**32 - 1, 2**32, 2**40, -1, -25, -1000):
            self.assertEqual(cbor_decode(enc(n)), n)

    def test_text_string_and_byte_string_both_become_str(self):
        self.assertEqual(cbor_decode(b"\x63abc"), "abc")
        self.assertEqual(cbor_decode(b"\x43abc"), "abc")
        self.assertEqual(cbor_decode(b"\x42\xe9\xff"), "\xe9\xff")  # latin-1

    def test_simple_values_and_floats(self):
        self.assertEqual(cbor_decode(b"\xf4"), False)
        self.assertEqual(cbor_decode(b"\xf5"), True)
        self.assertIsNone(cbor_decode(b"\xf6"))
        self.assertEqual(cbor_decode(b"\xfb" + struct.pack(">d", 1.5)), 1.5)
        self.assertEqual(cbor_decode(b"\xfa" + struct.pack(">f", 2.5)), 2.5)
        self.assertEqual(cbor_decode(b"\xf9\x3c\x00"), 1.0)  # half precision

    def test_trailing_bytes_raise(self):
        with self.assertRaises(ValueError):
            cbor_decode(payload() + b"\x00")

    def test_truncated_data_raises(self):
        for cut in (1, 5, len(payload()) - 1):
            with self.assertRaises(ValueError):
                cbor_decode(payload()[:cut])
        with self.assertRaises(ValueError):
            cbor_decode(b"")

    def test_unknown_types_raise(self):
        for bad in (b"\xc1\x00",      # tag (major 6)
                    b"\x5f\x41a\xff",  # indefinite-length byte string
                    b"\xf7",           # undefined
                    b"\x1c",           # reserved additional info
                    b"\xa1\x80\x01"):  # array as a map key
            with self.assertRaises(ValueError, msg=bad.hex()):
                cbor_decode(bad)

    def test_deep_nesting_raises_value_error(self):
        with self.assertRaises(ValueError):
            cbor_decode(b"\x81" * 10000 + b"\x00")


class RealmsTests(unittest.TestCase):
    def test_lists_realm_keys_and_skips_dbversion(self):
        raw = lua_file({"TestRealm": payload(), "OtherRealm": payload({})})
        self.assertEqual(realms(raw), ["TestRealm", "OtherRealm"])

    def test_no_database(self):
        self.assertEqual(realms(b"SOMETHING_ELSE = {\r\n}\r\n"), [])
        self.assertEqual(realms(b"AUCTIONATOR_PRICE_DATABASE = {\r\n[\"__dbversion\"] = 8,\r\n}\r\n"), [])

    def test_the_payload_has_the_awkward_bytes(self):
        p = payload()
        for b in (0x0D, 0x0A, 0x5C, 0x22, 0x00, 0xC8):
            self.assertIn(bytes([b]), p, hex(b))
        raw = lua_file({"TestRealm": p})
        self.assertIn(b"\\r", raw)
        self.assertIn(b"\\n", raw)
        self.assertIn(b"\\\\", raw)
        self.assertIn(b'\\"', raw)
        self.assertRegex(raw, rb"\\\d\d\d")

    def test_whole_payload_survives_escaping(self):
        raw = lua_file({"TestRealm": payload()})
        self.assertEqual(lua_string_at(raw, b"TestRealm"), payload())
        self.assertEqual(cbor_decode(lua_string_at(raw, b"TestRealm")), realm_data())

    def test_decoy_in_a_later_table_is_not_a_realm(self):
        raw = lua_file({"TestRealm": payload()})
        self.assertNotIn("decoy", realms(raw))
        self.assertEqual(realms(raw), ["TestRealm"])


class LoadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, realm_payloads: dict[str, bytes], text: bytes | None = None) -> Path:
        p = self.dir / "Auctionator.lua"
        p.write_bytes(text if text is not None else lua_file(realm_payloads))
        return p

    def test_prices_and_quantities(self):
        m = load_auctionator(self.write({"TestRealm": payload()}), None)
        self.assertEqual(m.source, "auctionator")
        self.assertEqual(m.listings, {2840: [(1250, 3)],   # quantity at the latest day, not the older one
                                      2841: [(300, 4)], 2842: [(200, 2)],
                                      13: [(13, 10)], 14: [(34, 92)]})
        self.assertEqual(m.buy_cost(2840, 3), 3750)
        self.assertIsNone(m.buy_cost(2840, 4))

    def test_scan_day_is_newest_over_a_h_and_l(self):
        m = load_auctionator(self.write({"TestRealm": payload()}), None)
        self.assertEqual(m.scan_day, "2026-11-18")
        self.assertEqual(m.snapshot_time, "2026-11-18")
        # the newest day appears only in an item's h here
        data = {"1": item(5, {NEWEST - 2: 1}, h={NEWEST: 9})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(m.scan_day, "2026-11-18")
        data = {"1": item(5, {NEWEST - 2: 1}, l={NEWEST + 1: 9})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(m.scan_day, "2026-11-19")

    def test_old_and_empty_items_are_dropped_and_counted(self):
        m = load_auctionator(self.write({"TestRealm": payload()}), None)
        self.assertEqual(m.dropped, 2)  # 4 days old; a == 0
        self.assertNotIn(2843, m.listings)
        self.assertNotIn(2844, m.listings)

    def test_version_and_non_digit_keys_are_skipped_not_counted(self):
        data = {"version": 2, "g:7": {"x": 1}, "5": item(9, {NEWEST: 1})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(m.listings, {5: [(9, 1)]})
        self.assertEqual(m.dropped, 0)

    def test_item_without_availability_is_dropped(self):
        data = {"5": item(9, {NEWEST: 1}), "6": {"m": 4, "a": []}, "7": {"m": 4}}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(list(m.listings), [5])
        self.assertEqual(m.dropped, 2)

    def test_item_keys_must_be_ascii_digits(self):
        data = {"5": item(9, {NEWEST: 1}), "\xb2": item(9, {NEWEST: 1}), "1.5": item(9, {NEWEST: 1}),
                " 7": item(9, {NEWEST: 1})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(list(m.listings), [5])
        self.assertEqual(m.dropped, 0)

    def test_item_without_a_usable_price_is_dropped_and_counted(self):
        data = {"5": item(9, {NEWEST: 1}), "6": {"a": {str(NEWEST): 1}}, "7": item(0, {NEWEST: 1}),
                "8": item(True, {NEWEST: 1}), "9": item("12", {NEWEST: 1})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(list(m.listings), [5])
        self.assertEqual(m.dropped, 4)

    def test_boolean_quantity_is_not_a_quantity(self):
        data = {"5": item(9, {NEWEST: 1}), "6": item(9, {NEWEST: True})}
        m = load_auctionator(self.write({"R": payload(data)}), None)
        self.assertEqual(list(m.listings), [5])
        self.assertEqual(m.dropped, 1)

    def test_a_day_key_that_is_not_a_day_is_a_value_error(self):
        for bad in (float("inf"), float("nan"), "x"):
            data = {"5": {"m": 9, "a": {bad: 1}}}
            with self.assertRaises(ValueError, msg=repr(bad)):
                load_auctionator(self.write({"R": payload(data)}), None)

    def test_several_realms_need_a_choice(self):
        path = self.write({"TestRealm": payload(), "OtherRealm": payload({})})
        with self.assertRaises(ValueError) as cm:
            load_auctionator(path, None)
        self.assertEqual(str(cm.exception),
                         "several realms in Auctionator.lua: TestRealm, OtherRealm; pass --realm")
        m = load_auctionator(path, "TestRealm")
        self.assertEqual(len(m.listings), 5)

    def test_unknown_realm_names_the_known_ones(self):
        path = self.write({"TestRealm": payload(), "OtherRealm": payload({})})
        with self.assertRaises(ValueError) as cm:
            load_auctionator(path, "Nope")
        self.assertIn("TestRealm, OtherRealm", str(cm.exception))

    def test_no_database(self):
        path = self.write({}, text=b"SOMETHING = {\r\n}\r\n")
        with self.assertRaises(ValueError) as cm:
            load_auctionator(path, None)
        self.assertEqual(str(cm.exception), "no price database in Auctionator.lua: "
                                            "open the AH with Auctionator and scan first")

    def test_trailing_garbage_in_the_payload_raises(self):
        path = self.write({"TestRealm": payload() + b"\x01"})
        with self.assertRaises(ValueError):
            load_auctionator(path, None)

    def test_payload_that_is_not_a_map_raises(self):
        with self.assertRaises(ValueError):
            load_auctionator(self.write({"TestRealm": enc([1, 2])}), None)

    def test_empty_database_gives_no_scan_day(self):
        m = load_auctionator(self.write({"TestRealm": payload({"version": 2})}), None)
        self.assertEqual((m.listings, m.scan_day, m.dropped), ({}, "", 0))

    def test_single_realm_with_text_before_the_table(self):
        raw = b"OTHER = {\r\n\t[\"TestRealm\"] = \"x\",\r\n}\r\n" + lua_file({"TestRealm": payload()})
        m = load_auctionator(self.write({}, text=raw), None)
        self.assertEqual(len(m.listings), 5)


class MarketFieldsTests(unittest.TestCase):
    def test_defaults(self):
        m = Market({})
        self.assertEqual((m.source, m.scan_day, m.dropped), ("api", "", 0))

    def test_fields_survive_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            m = Market({5: [(9, 1)]}, "2026-11-18")
            m.source, m.scan_day, m.dropped = "auctionator", "2026-11-18", 3
            m.save(Path(d) / "p.json")
            back = Market.load(Path(d) / "p.json")
        self.assertEqual((back.source, back.scan_day, back.dropped), ("auctionator", "2026-11-18", 3))

    def test_old_prices_file_without_the_fields_still_loads(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.json"
            p.write_text('{"snapshot_time": "t", "house": 1, "listings": {"5": [[9, 1]]}}', encoding="utf-8")
            m = Market.load(p)
        self.assertEqual((m.source, m.scan_day, m.dropped), ("api", "", 0))


def run(argv, paths):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv, paths)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.paths = settings.paths(self.dir / "home")

    def tearDown(self):
        self._tmp.cleanup()

    def file(self, realm_payloads: dict[str, bytes]) -> str:
        p = self.dir / "Auctionator.lua"
        p.write_bytes(lua_file(realm_payloads))
        return str(p)

    def test_import_writes_the_normal_prices_file(self):
        code, out = run(["prices", "--auctionator", self.file({"TestRealm": payload()})], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn("5 items", out)
        self.assertIn("2026-11-18", out)
        self.assertIn("2 left out", out)
        m = Market.load(self.paths.prices)
        self.assertEqual((m.source, m.scan_day, m.dropped, m.house), ("auctionator", "2026-11-18", 2, None))
        self.assertEqual(m.min_price(2840), 1250)

    def test_import_needs_no_profile_or_credentials(self):
        self.assertFalse(self.paths.profile.exists())
        code, _ = run(["prices", "--auctionator", self.file({"TestRealm": payload()})], self.paths)
        self.assertEqual(code, 0)

    def test_several_realms_exit_1_with_the_keys(self):
        f = self.file({"TestRealm": payload(), "OtherRealm": payload({})})
        code, out = run(["prices", "--auctionator", f], self.paths)
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "several realms in Auctionator.lua: TestRealm, OtherRealm; pass --realm")
        self.assertFalse(self.paths.prices.exists())
        code, out = run(["prices", "--auctionator", f, "--realm", "OtherRealm"], self.paths)
        self.assertEqual(code, 0, out)

    def test_no_database_exit_1(self):
        p = self.dir / "Auctionator.lua"
        p.write_bytes(b"X = {\r\n}\r\n")
        code, out = run(["prices", "--auctionator", str(p)], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("no price database in Auctionator.lua: open the AH with Auctionator and scan first", out)

    def test_missing_file_exit_1_without_traceback(self):
        code, out = run(["prices", "--auctionator", str(self.dir / "nope.lua")], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("nope.lua", out)

    def test_damaged_payload_exit_1_without_traceback(self):
        code, out = run(["prices", "--auctionator", self.file({"TestRealm": payload() + b"\x00"})], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("Auctionator.lua", out)

    def test_realm_without_auctionator_is_refused(self):
        code, out = run(["prices", "--realm", "TestRealm"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("--auctionator", out)

    def test_prices_without_the_flag_is_unchanged(self):
        run(["init"], self.paths)
        code, out = run(["prices"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("probe"), out)


if __name__ == "__main__":
    unittest.main()
