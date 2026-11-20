import json
import os
import tempfile
import unittest
from pathlib import Path

from yap_forever import config, settings


def write_creds(path: Path, data: dict, mode: int) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(path, mode)
    return path


class HomeTests(unittest.TestCase):
    def test_home_default(self):
        self.assertEqual(settings.home({}), Path.home() / ".yap-forever")

    def test_home_env_override(self):
        self.assertEqual(settings.home({"YAP_FOREVER_HOME": "/x"}), Path("/x"))

    def test_paths_layout(self):
        p = settings.paths(Path("/r"))
        self.assertEqual(p.character("Ana"), Path("/r/characters/Ana"))
        self.assertEqual(p.prices, Path("/r/cache/prices.json"))
        from yap_forever.gamedata import PIN_KEY
        self.assertEqual(p.gamedata, Path("/r/cache/gamedata") / PIN_KEY)
        self.assertEqual(p.credentials, Path("/r/credentials.json"))
        self.assertEqual(p.house, Path("/r/house.json"))
        self.assertEqual(p.reports, Path("/r/reports"))
        self.assertEqual(p.remote, Path("/r/remote.toml"))

    def test_paths_default_follows_env(self):
        self.assertEqual(settings.paths().root, Path(os.environ["YAP_FOREVER_HOME"]))

    def test_home_with_space_and_cyrillic(self):
        with tempfile.TemporaryDirectory() as d:
            p = settings.paths(Path(d) / "Мой дом" / "yap")
            stock = p.character("Аня") / "stock.toml"
            stock.parent.mkdir(parents=True)
            stock.write_text("# запасы\nlevel = 12\n[items]\n2589 = 40\n", encoding="utf-8")
            s = config.load_stock(stock)
        self.assertEqual(s.level, 12)
        self.assertEqual(s.items[2589], 40)


class RemoteTests(unittest.TestCase):
    def load(self, text: str | None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "remote.toml"
            if text is not None:
                p.write_text(text, encoding="utf-8")
            return settings.load_remote(p)

    def test_host_only_fills_defaults(self):
        self.assertEqual(self.load('host = "example-host"\n'), settings.Remote(
            host="example-host", key=None,
            command="cd yap-forever && git pull -q && cd plugin && python3 -m yap_forever prices",
            remote_file=".yap-forever/cache/prices.json"))

    def test_missing_file_is_none(self):
        self.assertIsNone(self.load(None))

    def test_all_keys(self):
        r = self.load('host = "me@example-host"\nkey = "/keys/id_demo"\n'
                      'command = "run it"\nremote_file = "out/p.json"\n')
        self.assertEqual((r.host, r.key, r.command, r.remote_file),
                         ("me@example-host", "/keys/id_demo", "run it", "out/p.json"))

    def test_key_expands_home(self):
        r = self.load('host = "example-host"\nkey = "~/.ssh/id_demo"\n')
        self.assertEqual(r.key, str(Path("~/.ssh/id_demo").expanduser()))

    def test_empty_host_refused(self):
        for text in ('host = ""\n', 'host = "  "\n', 'command = "x"\n'):
            with self.subTest(text=text), self.assertRaises(ValueError) as cm:
                self.load(text)
            self.assertIn("host", str(cm.exception))


    def test_non_text_or_empty_values_refused(self):
        cases = (('host = 5\n', "host"), ('host = "h"\ncommand = 1\n', "command"),
                 ('host = "h"\nremote_file = ["a"]\n', "remote_file"),
                 ('host = "h"\nkey = 7\n', "key"), ('host = "h"\ncommand = "  "\n', "command"))
        for text, name in cases:
            with self.subTest(text=text), self.assertRaises(ValueError) as cm:
                self.load(text)
            self.assertIn("remote.toml", str(cm.exception))
            self.assertIn(name, str(cm.exception))


class CredentialsTests(unittest.TestCase):
    GOOD = {"client_id": "id", "client_secret": "secret"}

    @unittest.skipIf(os.name == "nt", "file modes are POSIX only")
    def test_credentials_mode_refused_posix(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_creds(Path(d) / "credentials.json", self.GOOD, 0o644)
            with self.assertRaises(PermissionError) as cm:
                settings.load_credentials(p, os_name="posix")
        self.assertIn("chmod 600", str(cm.exception))

    def test_credentials_mode_ignored_on_windows(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_creds(Path(d) / "credentials.json", self.GOOD, 0o644)
            c = settings.load_credentials(p, os_name="nt")
        self.assertEqual(c.region, "eu")

    def test_credentials_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_creds(Path(d) / "credentials.json", {"client_id": "", "client_secret": ""}, 0o600)
            with self.assertRaises(ValueError) as cm:
                settings.load_credentials(p)
        self.assertIn("fill in client_id and client_secret", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
