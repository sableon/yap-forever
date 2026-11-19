"""Read prices from the Auctionator addon's saved variables (Auctionator.lua).

Auctionator keeps one entry per realm in AUCTIONATOR_PRICE_DATABASE. Each value is a Lua string
holding CBOR bytes: a map of item ID -> {m: latest minimum buyout in copper, a: {day: quantity
available}, h: {day: high}, l: {day: low}}, plus a "version" key. Days count from 2020-01-01.
The file is not valid UTF-8, so everything here works on bytes. Stdlib only.
"""
import collections
import datetime
import re
import struct
from pathlib import Path

from yap_forever.prices import FRESH_DAYS, Market

EPOCH = datetime.date(2020, 1, 1)
NO_DATABASE = "no price database in Auctionator.lua: open the AH with Auctionator and scan first"

_TABLE = re.compile(rb"AUCTIONATOR_PRICE_DATABASE\s*=\s*\{")
_KEY = re.compile(rb'\s*,?\s*\["([^"\r\n]*)"\]\s*=\s*')
_END = re.compile(rb"\s*,?\s*\}")
_PLAIN = re.compile(rb"[^,}\r\n]*")
_STRING = re.compile(rb'"([^"\\]*(?:\\(?:\r\n|.)[^"\\]*)*)"', re.DOTALL)
_ESCAPE = re.compile(rb"\\(\d{1,3}|\r\n|.)", re.DOTALL)
_SIMPLE = {ord(c): v for c, v in (("n", 10), ("r", 13), ("t", 9), ("\\", 92), ('"', 34), ("'", 39),
                                  ("a", 7), ("b", 8), ("f", 12), ("v", 11), ("\n", 10), ("\r", 10))}
_MAX_DEPTH = 100


def _unescape(body: bytes) -> bytes:
    def one(m: re.Match) -> bytes:
        e = m.group(1)
        if e[0:1].isdigit():
            n = int(e)
            if n > 255:
                raise ValueError(f"Lua escape \\{e.decode()} is not a byte")
            return bytes([n])
        if e == b"\r\n":
            return b"\n"
        if e[0] in _SIMPLE:
            return bytes([_SIMPLE[e[0]]])
        raise ValueError(f"unknown Lua escape \\{e.decode('latin-1')}")
    return _ESCAPE.sub(one, body)


def _entries(raw: bytes):
    """Yield (key, string literal body or None) for each entry of the price database table."""
    t = _TABLE.search(raw)
    if t is None:
        return
    pos = t.end()
    while True:
        k = _KEY.match(raw, pos)
        if k is None:
            if _END.match(raw, pos):
                return
            raise ValueError("Auctionator.lua: cannot read the price database table")
        pos = k.end()
        s = _STRING.match(raw, pos) if raw[pos:pos + 1] == b'"' else None
        if s is not None:
            pos = s.end()
            yield k.group(1), s.group(1)
        elif raw[pos:pos + 1] == b'"':
            raise ValueError("Auctionator.lua: a string in the price database is not closed")
        else:  # a plain value such as ["__dbversion"] = 8
            pos = _PLAIN.match(raw, pos).end()
            yield k.group(1), None


def lua_string_at(raw: bytes, key: bytes) -> bytes:
    """The unescaped bytes of the string stored under `key` in the price database table."""
    for k, body in _entries(raw):
        if k == key and body is not None:
            return _unescape(body)
    raise ValueError(f"no string for {key.decode('utf-8', 'replace')!r} in the Auctionator price database")


def realms(raw: bytes) -> list[str]:
    """Realm keys of the price database (entries holding a string; __dbversion is a number)."""
    return [k.decode("utf-8", "replace") for k, body in _entries(raw) if body is not None]


def _cbor(b: bytes, i: int, depth: int):
    if depth > _MAX_DEPTH:
        raise ValueError("CBOR nested too deeply")
    if i >= len(b):
        raise ValueError("CBOR ends early")
    mt, ai = b[i] >> 5, b[i] & 31
    i += 1
    if mt == 7 and ai in (20, 21, 22):
        return (False, True, None)[ai - 20], i
    if ai < 24:
        v = ai
    elif ai in (24, 25, 26, 27):
        n = 1 << (ai - 24)
        if i + n > len(b):
            raise ValueError("CBOR ends early")
        if mt == 7:
            if ai == 24:
                raise ValueError("CBOR simple value not supported")
            return struct.unpack({25: ">e", 26: ">f", 27: ">d"}[ai], b[i:i + n])[0], i + n
        v = int.from_bytes(b[i:i + n], "big")
        i += n
    else:
        raise ValueError(f"CBOR additional info {ai} not supported")
    if mt == 0:
        return v, i
    if mt == 1:
        return -1 - v, i
    if mt in (2, 3):
        if i + v > len(b):
            raise ValueError("CBOR ends early")
        # latin-1 on purpose: Auctionator writes byte strings, and every byte must map to a character
        return b[i:i + v].decode("latin-1"), i + v
    if mt == 4:
        out = []
        for _ in range(v):
            x, i = _cbor(b, i, depth + 1)
            out.append(x)
        return out, i
    if mt == 5:
        d = {}
        for _ in range(v):
            k, i = _cbor(b, i, depth + 1)
            if isinstance(k, (list, dict)):
                raise ValueError("CBOR map key is not a plain value")
            d[k], i = _cbor(b, i, depth + 1)
        return d, i
    raise ValueError(f"CBOR major type {mt} not supported")


def cbor_decode(data: bytes):
    """Decode one CBOR value: integers, strings (both kinds become str), arrays, maps, floats,
    true/false/null. Raises ValueError on anything else, truncated data or trailing bytes."""
    value, end = _cbor(data, 0, 0)
    if end != len(data):
        raise ValueError(f"CBOR has {len(data) - end} unused bytes after the value")
    return value


def _days(x) -> dict[int, object]:
    """{day: value} from an Auctionator day map; an empty one may be stored as an empty array."""
    if not isinstance(x, dict):
        return {}
    out = {}
    for k, v in x.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Auctionator day {k!r} is not a number") from None
    return out


def load_auctionator(path: Path, realm: str | None) -> Market:
    """Build a Market from Auctionator.lua: one price (m) and one quantity (latest day of a) per item.

    scan_day is the bulk day: the most common latest-a day among the items (a tie goes to the newer day),
    which is the day of the full scan. A later partial scan doesn't move it. An item is kept when its latest
    a day is within FRESH_DAYS of that day or newer, and its quantity there is above 0 and it has a usable
    price; the rest count in Market.dropped.
    """
    raw = Path(path).read_bytes()
    keys = realms(raw)
    if realm is None:
        if not keys:
            raise ValueError(NO_DATABASE)
        if len(keys) > 1:
            raise ValueError(f"several realms in Auctionator.lua: {', '.join(keys)}; pass --realm")
        realm = keys[0]
    elif realm not in keys:
        raise ValueError(f"no realm {realm!r} in Auctionator.lua: " +
                         (", ".join(keys) if keys else NO_DATABASE))
    try:
        data = cbor_decode(lua_string_at(raw, realm.encode("utf-8")))
        if not isinstance(data, dict):
            raise ValueError("the realm's data is not a map")
        items = {k: v for k, v in data.items() if isinstance(k, str) and k.isascii() and k.isdigit()}
        parsed = {}
        for k, v in items.items():
            if not isinstance(v, dict):
                parsed[int(k)] = None
                continue
            parsed[int(k)] = (v.get("m"), _days(v.get("a")))
        latest = collections.Counter(max(e[1]) for e in parsed.values() if e is not None and e[1])
        anchor = max(latest, key=lambda day: (latest[day], day)) if latest else None
        scan_day = ""
        if anchor is not None:
            try:
                scan_day = (EPOCH + datetime.timedelta(days=anchor)).isoformat()
            except OverflowError:
                raise ValueError(f"Auctionator day {anchor} is out of range") from None
    except ValueError as e:
        raise ValueError(f"Auctionator.lua is damaged ({e}): scan again with Auctionator") from None
    listings: dict[int, list[tuple[int, int]]] = {}
    for item_id, entry in parsed.items():
        if entry is None or not entry[1]:
            continue
        m, a = entry
        last = max(a)
        qty = a[last]
        if (last >= anchor - FRESH_DAYS and isinstance(qty, int) and not isinstance(qty, bool) and qty > 0
                and isinstance(m, int) and not isinstance(m, bool) and m > 0):
            listings[item_id] = [(m, qty)]
    market = Market(listings, scan_day)
    market.source = "auctionator"
    market.scan_day = scan_day
    market.dropped = len(parsed) - len(listings)
    return market
