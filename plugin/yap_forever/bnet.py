"""Minimal Battle.net API client for WoW: Forever auction data.

Never prints or logs the client ID, secret or token.
"""
import base64
import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

from yap_forever import settings
from yap_forever.config import Credentials

TOKEN_URL = "https://oauth.battle.net/token"
AUTH_MESSAGE = "Battle.net rejected the client ID/secret — check the client at develop.battle.net"


class AuthError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status: int, path: str, reason: str = ""):
        msg = (f"could not reach the Battle.net API for {path} ({reason}) — check your network or VPN"
               if status == 0 else f"API returned {status} for {path}")
        super().__init__(msg)
        self.status = status
        self.path = path


@dataclass
class Response:
    status: int
    body: dict | None
    last_modified: str | None


class Client:
    def __init__(self, creds: Credentials, opener=urllib.request.urlopen, now=time.time,
                 token_cache: Path | None = None, region: str | None = None):
        self.creds = creds
        self.opener = opener
        self.now = now
        self.token_cache = Path(token_cache) if token_cache is not None else settings.paths().token
        self.region = region or creds.region
        self.host = f"https://{self.region}.api.blizzard.com"
        self.namespace = namespace(self.region)

    # --- token -------------------------------------------------------------
    def _cached_token(self) -> str | None:
        try:
            d = json.loads(self.token_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if d.get("expires_at", 0) - 60 > self.now():
            return d.get("access_token")
        return None

    def _new_token(self) -> str:
        basic = base64.b64encode(f"{self.creds.client_id}:{self.creds.client_secret}".encode()).decode()
        req = urllib.request.Request(
            TOKEN_URL, data=b"grant_type=client_credentials", method="POST",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener(req, timeout=30) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            e.close()
            if e.code in (400, 401, 403):
                raise AuthError(AUTH_MESSAGE) from None
            raise ApiError(e.code, "/token") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ApiError(0, "/token", str(getattr(e, "reason", e))) from None
        token = d["access_token"]
        self.token_cache.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.token_cache, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"access_token": token, "expires_at": self.now() + d.get("expires_in", 0)}, f)
        os.chmod(self.token_cache, 0o600)
        return token

    def token(self) -> str:
        return self._cached_token() or self._new_token()

    # --- requests ----------------------------------------------------------
    def get(self, path: str, if_modified_since: str | None = None) -> Response:
        try:
            return self._get(path, if_modified_since)
        except AuthError:
            # A cached token from an old or rotated client: drop it and retry once.
            self.token_cache.unlink(missing_ok=True)
            return self._get(path, if_modified_since)

    def _get(self, path: str, if_modified_since: str | None = None) -> Response:
        headers = {"Authorization": f"Bearer {self.token()}",
                   "Battlenet-Namespace": self.namespace,
                   "Accept-Encoding": "gzip"}
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since
        req = urllib.request.Request(self.host + path, headers=headers)
        try:
            with self.opener(req, timeout=120) as r:
                raw = r.read()
                hdrs = r.headers
            if hdrs.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            body = json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 304:
                return Response(304, None, if_modified_since)
            if e.code == 401:
                raise AuthError(AUTH_MESSAGE) from None
            raise ApiError(e.code, path) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ApiError(0, path, str(getattr(e, "reason", e))) from None
        except (EOFError, ValueError, zlib.error) as e:  # cut off or garbled on the way
            raise ApiError(0, path, f"damaged response: {e}") from None
        return Response(200, body, hdrs.get("Last-Modified"))


def namespace(region: str) -> str:
    return f"dynamic-forever-{region}"


def index_path(ruleset: int) -> str:
    return f"/data/wow/ruleset/{ruleset}/auctions/index"


def index_houses(index: dict) -> list[int]:
    return sorted(int(h["id"]) for h in (index or {}).get("auctions", []) if "id" in h)


def house_path(house: int, ruleset: int, commodities: bool = False) -> str:
    p = f"/data/wow/ruleset/{ruleset}/auctions/{house}"
    return p + "/commodities" if commodities else p


def find_marker(houses: dict[int, tuple[dict, dict]], item_id: int, buyout: int) -> list[int]:
    """House IDs whose regular buyout or commodity unit price equals the marker."""
    found = []
    for house, (regular, comm) in houses.items():
        hit = any(a.get("item", {}).get("id") == item_id and a.get("buyout") == buyout
                  for a in (regular or {}).get("auctions", []))
        hit = hit or any(a.get("item", {}).get("id") == item_id and a.get("unit_price") == buyout
                         for a in (comm or {}).get("auctions", []))
        if hit:
            found.append(house)
    return found
