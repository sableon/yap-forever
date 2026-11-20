import gzip
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path

from yap_forever import bnet
from yap_forever.config import Credentials

FIX = Path(__file__).parent / "fixtures"
CREDS = Credentials("myclientid", "s3cr3tvalue", "eu")


class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, headers=None, status=200):
        super().__init__(body)
        self.headers = headers or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Records requests; answers token calls and API calls from a script."""

    def __init__(self, api=None, token_status=200, expires_in=86399):
        self.token_calls = 0
        self.api_calls = []
        self.api = api or (lambda req: FakeResp(b'{"ok": 1}'))
        self.token_status = token_status
        self.expires_in = expires_in

    def __call__(self, req, timeout=None):
        if req.full_url.startswith("https://oauth.battle.net/token"):
            self.token_calls += 1
            if self.token_status != 200:
                raise urllib.error.HTTPError(req.full_url, self.token_status, "Unauthorized", {}, None)
            body = json.dumps({"access_token": f"tok{self.token_calls}", "expires_in": self.expires_in})
            return FakeResp(body.encode())
        self.api_calls.append(req)
        return self.api(req)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "token.json"

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, opener, now=lambda: 1000.0):
        return bnet.Client(CREDS, opener=opener, now=now, token_cache=self.cache)

    def test_token_cached_until_expiry(self):
        op = FakeOpener()
        c = self.client(op)
        c.get("/data/wow/ruleset/2/auctions/index")
        c.get("/data/wow/ruleset/2/auctions/index")
        self.assertEqual(op.token_calls, 1)
        if os.name != "nt":  # Windows has no POSIX file modes
            self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)

    def test_token_refreshed_when_expired(self):
        op = FakeOpener(expires_in=100)
        t = [1000.0]
        c = self.client(op, now=lambda: t[0])
        c.get("/x")
        t[0] = 1100.0
        c.get("/x")
        self.assertEqual(op.token_calls, 2)

    def test_401_raises_autherror_without_secret(self):
        op = FakeOpener(token_status=401)
        c = self.client(op)
        with self.assertRaises(bnet.AuthError) as cm:
            c.get("/x")
        self.assertNotIn("s3cr3tvalue", str(cm.exception))
        self.assertNotIn("myclientid", str(cm.exception))

    def test_304_returns_no_body(self):
        def api(req):
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)
        c = self.client(FakeOpener(api=api))
        r = c.get("/x", if_modified_since="Fri, 06 Nov 2026 09:17:16 GMT")
        self.assertEqual(r.status, 304)
        self.assertIsNone(r.body)

    def test_gzip_body_decoded(self):
        raw = gzip.compress(b'{"a": 5}')
        api = lambda req: FakeResp(raw, {"Content-Encoding": "gzip", "Last-Modified": "X"})
        c = self.client(FakeOpener(api=api))
        r = c.get("/x")
        self.assertEqual(r.body, {"a": 5})
        self.assertEqual(r.last_modified, "X")

    def test_request_headers(self):
        op = FakeOpener()
        c = self.client(op)
        c.get("/data/wow/ruleset/2/auctions/10")
        req = op.api_calls[0]
        self.assertEqual(req.full_url, "https://eu.api.blizzard.com/data/wow/ruleset/2/auctions/10")
        self.assertEqual(req.get_header("Battlenet-namespace"), "dynamic-forever-eu")
        self.assertEqual(req.get_header("Authorization"), "Bearer tok1")

    def test_404_raises_apierror(self):
        def api(req):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        c = self.client(FakeOpener(api=api))
        with self.assertRaises(bnet.ApiError) as cm:
            c.get("/x")
        self.assertEqual(cm.exception.status, 404)

    def test_stale_token_replaced_after_401(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "token.json"
            cache.write_text(json.dumps({"access_token": "old", "expires_at": 10 ** 12}))
            calls = []

            def api(req):
                calls.append(req.get_header("Authorization"))
                if req.get_header("Authorization") == "Bearer old":
                    raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
                return FakeResp(b'{"ok": 1}')
            op = FakeOpener(api=api)
            c = bnet.Client(Credentials("a", "b", "eu"), opener=op, now=lambda: 1000.0, token_cache=cache)
            self.assertEqual(c.get("/x").body, {"ok": 1})
            self.assertEqual(op.token_calls, 1)


class MarkerTests(unittest.TestCase):
    def load(self):
        house = json.loads((FIX / "house_small.json").read_text())
        comm = json.loads((FIX / "commodities_small.json").read_text())
        return house, comm

    def test_find_marker_regular(self):
        house, comm = self.load()
        houses = {10: ({}, {}), 20: (house, {}), 30: ({}, comm)}
        self.assertEqual(bnet.find_marker(houses, 2589, 71313), [20])

    def test_find_marker_commodity(self):
        house, comm = self.load()
        houses = {10: ({}, {}), 20: (house, {}), 30: ({}, comm)}
        self.assertEqual(bnet.find_marker(houses, 2770, 777), [30])

    def test_find_marker_empty_house(self):
        houses = {10: ({"id": 10, "name": "Alliance Auction House"}, {})}
        self.assertEqual(bnet.find_marker(houses, 2589, 71313), [])


if __name__ == "__main__":
    unittest.main()


class NetworkErrorTests(unittest.TestCase):
    def test_network_error_becomes_apierror(self):
        def api(req):
            raise urllib.error.URLError("_ssl.c:1126: The handshake operation timed out")
        with tempfile.TemporaryDirectory() as d:
            c = bnet.Client(CREDS, opener=FakeOpener(api=api), now=lambda: 1000.0,
                            token_cache=Path(d) / "t.json")
            with self.assertRaises(bnet.ApiError) as cm:
                c.get("/x")
        self.assertEqual(cm.exception.status, 0)
        self.assertIn("could not reach", str(cm.exception))


class OfflineTests(unittest.TestCase):
    def test_token_network_failure_is_api_error(self):
        def opener(req, timeout=None):
            raise urllib.error.URLError("no route to host")
        with tempfile.TemporaryDirectory() as d:
            c = bnet.Client(CREDS, opener=opener, token_cache=Path(d) / "t.json")
            with self.assertRaises(bnet.ApiError) as cm:
                c.get("/data/wow/ruleset/2/auctions/index")
        self.assertEqual(cm.exception.status, 0)
        self.assertIn("network", str(cm.exception))
