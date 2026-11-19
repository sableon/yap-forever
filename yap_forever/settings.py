"""Where a player's files live: one home folder, resolved when it is needed.

Default `~/.yap-forever/`; the YAP_FOREVER_HOME environment variable overrides it.
Nothing here is computed at import time, so tests and players can point it elsewhere.
"""
import json
import os
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from yap_forever.config import Credentials

HOME_ENV = "YAP_FOREVER_HOME"


def command_hint(args: str, os_name: str = os.name) -> str:
    """How the player runs a command on their system, for next-step messages."""
    python = "py -3" if os_name == "nt" else "python3"
    return f"{python} -m yap_forever {args}"


def home(env: Mapping[str, str] = os.environ) -> Path:
    value = env.get(HOME_ENV)
    return Path(value) if value else Path.home() / ".yap-forever"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def credentials(self) -> Path:
        return self.root / "credentials.json"

    @property
    def profile(self) -> Path:
        return self.root / "profile.toml"

    @property
    def remote(self) -> Path:
        return self.root / "remote.toml"

    @property
    def house(self) -> Path:
        return self.root / "house.json"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def gamedata(self) -> Path:
        return self.cache / "gamedata"

    @property
    def prices(self) -> Path:
        return self.cache / "prices.json"

    @property
    def token(self) -> Path:
        return self.cache / "token.json"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    def character(self, name: str) -> Path:
        return self.root / "characters" / name


def paths(root: Path | None = None) -> Paths:
    return Paths(Path(root) if root is not None else home())


def load_credentials(path: Path | None = None, os_name: str = os.name) -> Credentials:
    """Read the player's Blizzard API client. Never prints the values."""
    path = Path(path) if path is not None else paths().credentials
    if os_name != "nt":  # Windows has no POSIX modes; the file sits in the player's own profile
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            raise PermissionError(f"{path.name} must be readable only by you: run chmod 600 on it")
    data = json.loads(path.read_text(encoding="utf-8"))
    cid, secret = data.get("client_id", ""), data.get("client_secret", "")
    if not cid or not secret:
        raise ValueError(f"fill in client_id and client_secret in {path.name}")
    return Credentials(cid, secret, data.get("region", "eu"))


REMOTE_COMMAND = "cd yap-forever && git pull -q && python3 -m yap_forever prices"
REMOTE_FILE = ".yap-forever/cache/prices.json"


@dataclass(frozen=True)
class Remote:
    """A machine that fetches prices when this one can't reach the API (remote.toml)."""
    host: str
    key: str | None = None  # ssh key file, `~` already expanded
    command: str = REMOTE_COMMAND
    remote_file: str = REMOTE_FILE  # where that machine leaves its prices, relative to its login folder


def load_remote(path: Path) -> Remote | None:
    """Read remote.toml; None when the player has none."""
    path = Path(path)
    if not path.exists():
        return None
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    for name in ("host", "command", "remote_file"):
        if name in d and not isinstance(d[name], str):
            raise ValueError(f"{name} in {path.name} must be text, e.g. {name} = \"...\"")
    host = d.get("host", "").strip()
    if not host:
        raise ValueError(f"fill in host in {path.name}")
    command = d.get("command", REMOTE_COMMAND)
    if not command.strip():
        raise ValueError(f"command in {path.name} is empty: give the command to run there, or leave it out")
    key = d.get("key")
    if key is not None and not isinstance(key, str):
        raise ValueError(f"key in {path.name} must be text, e.g. key = \"~/.ssh/id_example\"")
    if key and key.startswith("~"):
        key = str(Path(key).expanduser())  # any other key path stays as the player typed it
    return Remote(host, key or None, command, d.get("remote_file", REMOTE_FILE))
