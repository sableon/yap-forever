import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yap_forever import cli, remote, settings
from yap_forever.prices import Market
from yap_forever.settings import Remote

GOOD = json.dumps({"snapshot_time": "t", "house": 7, "region": "eu", "ruleset": 2,
                   "listings": {"2840": [[10, 2]]}})


class Result:
    def __init__(self, returncode=0):
        self.returncode = returncode


class FakeRun:
    """Records argv; the scp step writes `payload` into the destination argument."""
    def __init__(self, payload: str | bytes = GOOD, codes=(0, 0), raises=None):
        self.calls, self.kwargs = [], []
        self.payload, self.codes, self.raises = payload, list(codes), raises

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)
        if self.raises:
            raise self.raises
        code = self.codes[len(self.calls) - 1]
        if argv[0] == "scp" and code == 0:
            data = self.payload if isinstance(self.payload, bytes) else self.payload.encode()
            (Path(kwargs.get("cwd", ".")) / argv[-1]).write_bytes(data)
        return Result(code)


def with_openssh(f):
    return mock.patch("yap_forever.remote.shutil.which", lambda name: "/usr/bin/" + name)(f)


class FetchRemoteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.dest = self.dir / "cache" / "prices.json"
        self.r = Remote("alice-box.test", None, "run-it", "out/prices.json")

    def tearDown(self):
        self._tmp.cleanup()

    def go(self, run, r=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = remote.fetch_remote(r or self.r, self.dest, run=run)
        return code, out.getvalue()

    @with_openssh
    def test_runs_ssh_then_scp_and_saves(self):
        run = FakeRun()
        code, out = self.go(run)
        self.assertEqual(code, 0, out)
        self.assertEqual(run.calls[0], ["ssh", "alice-box.test", "run-it"])
        self.assertEqual(run.calls[1][:2], ["scp", "alice-box.test:out/prices.json"])
        self.assertEqual(Market.load(self.dest).min_price(2840), 10)
        self.assertEqual(os.listdir(self.dest.parent), ["prices.json"])  # temp file gone
        self.assertIn("1 items", out)
        self.assertNotIn("example.test", out)

    @with_openssh
    def test_scp_runs_in_the_destination_folder_with_a_bare_target(self):
        # a drive letter on the scp command line (C:\\...) would read as a host name on Windows
        run = FakeRun()
        self.go(run)
        target = run.calls[1][-1]
        self.assertNotIn(os.sep, target)
        self.assertNotIn("/", target)
        self.assertNotIn(":", target)
        self.assertEqual(Path(run.kwargs[1]["cwd"]), self.dest.parent)

    @with_openssh
    def test_timeouts_and_no_stdin_for_ssh(self):
        run = FakeRun()
        self.go(run)
        self.assertEqual(run.kwargs[0]["timeout"], remote.SSH_TIMEOUT)
        self.assertEqual(run.kwargs[1]["timeout"], remote.SCP_TIMEOUT)
        self.assertIs(run.kwargs[0]["stdin"], subprocess.DEVNULL)

    @with_openssh
    def test_timeout_names_the_step(self):
        for step in ("ssh", "scp"):
            def run(argv, **kw):
                if argv[0] == step:
                    raise subprocess.TimeoutExpired(argv, kw["timeout"])
                return Result(0)
            code, out = self.go(run)
            self.assertEqual(code, 1)
            self.assertIn(f"the {step} step", out)
            self.assertIn("timed out", out)
            self.assertNotIn("example.test", out)

    @with_openssh
    def test_key_arguments(self):
        run = FakeRun()
        key = str(self.dir / "k")
        code, _ = self.go(run, Remote("h.test", key, "run-it", "f.json"))
        self.assertEqual(code, 0)
        self.assertEqual(run.calls[0], ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "h.test", "run-it"])
        self.assertEqual(run.calls[1][:5], ["scp", "-i", key, "-o", "IdentitiesOnly=yes"])
        self.assertEqual(run.calls[1][5], "h.test:f.json")

    @with_openssh
    def test_damaged_copy_leaves_dest_untouched(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.write_text(GOOD.replace("2840", "1111"), encoding="utf-8")
        before = self.dest.read_bytes()
        for payload in ("not json", b"\xff\xfe", '{"listings": 3}'):
            code, out = self.go(FakeRun(payload))
            self.assertEqual(code, 1, payload)
            self.assertIn("damaged", out)
            self.assertEqual(self.dest.read_bytes(), before)
            self.assertEqual(os.listdir(self.dest.parent), ["prices.json"])

    @with_openssh
    def test_empty_snapshot_is_refused_and_dest_kept(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.write_text(GOOD, encoding="utf-8")
        before = self.dest.read_bytes()
        empty = json.dumps({"snapshot_time": "t", "listings": {}})
        code, out = self.go(FakeRun(empty))
        self.assertEqual(code, 1)
        self.assertIn("no listings", out)
        self.assertEqual(self.dest.read_bytes(), before)
        self.assertEqual(os.listdir(self.dest.parent), ["prices.json"])

    @with_openssh
    def test_dest_unchanged_after_a_failed_step(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.write_text(GOOD, encoding="utf-8")
        before = self.dest.read_bytes()
        for codes in ((255, 0), (0, 1)):
            code, _ = self.go(FakeRun(codes=codes))
            self.assertEqual(code, 1)
            self.assertEqual(self.dest.read_bytes(), before)
            self.assertEqual(os.listdir(self.dest.parent), ["prices.json"])

    @with_openssh
    def test_temp_file_is_cleaned_after_a_runner_exception(self):
        self.dest.parent.mkdir(parents=True)
        with self.assertRaises(RuntimeError):
            self.go(FakeRun(raises=RuntimeError("boom")))
        self.assertEqual(os.listdir(self.dest.parent), [])

    @with_openssh
    def test_file_system_errors_are_a_message(self):
        self.dest.parent.parent.mkdir(parents=True, exist_ok=True)
        self.dest.parent.write_text("a file where the folder should be", encoding="utf-8")
        code, out = self.go(FakeRun())
        self.assertEqual(code, 1)
        self.assertIn("can't write", out)
        self.dest.parent.unlink()
        with mock.patch("yap_forever.remote.os.replace", side_effect=PermissionError(13, "Permission denied")):
            code, out = self.go(FakeRun())
        self.assertEqual(code, 1)
        self.assertIn("can't write", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(os.listdir(self.dest.parent), [])

    @with_openssh
    def test_blank_host_is_refused(self):
        run = FakeRun()
        code, out = self.go(run, Remote("  "))
        self.assertEqual(code, 1)
        self.assertEqual(run.calls, [])
        self.assertIn("host", out)

    @with_openssh
    def test_failing_step_is_named_and_stops(self):
        run = FakeRun(codes=(255, 0))
        code, out = self.go(run)
        self.assertEqual((code, len(run.calls)), (1, 1))
        self.assertIn("ssh", out)
        self.assertNotIn("scp", out)
        self.assertNotIn("example.test", out)
        self.assertFalse(self.dest.exists())
        run = FakeRun(codes=(0, 1))
        code, out = self.go(run)
        self.assertEqual((code, len(run.calls)), (1, 2))
        self.assertIn("scp", out)
        self.assertFalse(self.dest.exists())
        self.assertEqual(os.listdir(self.dest.parent), [])

    @with_openssh
    def test_runner_that_cannot_start_the_program(self):
        code, out = self.go(FakeRun(raises=FileNotFoundError("ssh")))
        self.assertEqual(code, 1)
        self.assertIn("ssh", out)
        self.assertNotIn("Traceback", out)

    def test_missing_openssh(self):
        for missing in ("ssh", "scp"):
            run = FakeRun()
            with mock.patch("yap_forever.remote.shutil.which",
                            lambda name, m=missing: None if name == m else "/x/" + name):
                code, out = self.go(run)
            self.assertEqual(code, 1)
            self.assertEqual(out.strip(), "remote fetch needs OpenSSH (ssh and scp) on your PATH")
            self.assertEqual(run.calls, [])

    @with_openssh
    def test_host_that_looks_like_an_option_is_refused(self):
        run = FakeRun()
        code, out = self.go(run, Remote("-oProxyCommand=x", None))
        self.assertEqual(code, 1)
        self.assertEqual(run.calls, [])
        self.assertIn("host", out)


def run_cli(argv, paths):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv, paths)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        self.paths.root.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_remote_toml_and_no_host_points_at_remote_toml(self):
        code, out = run_cli(["prices", "--remote"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("remote.toml", out)
        self.assertIn("--host", out)
        self.assertIn(str(self.paths.remote), out)

    def test_host_flag_alone_uses_defaults(self):
        calls = []
        with mock.patch("yap_forever.cli.remote.fetch_remote", lambda r, dest: calls.append((r, dest)) or 0):
            code, _ = run_cli(["prices", "--remote", "--host", "bob-box.test"], self.paths)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [(Remote("bob-box.test"), self.paths.prices)])

    def test_host_flag_is_stripped_and_blank_is_refused(self):
        calls = []
        with mock.patch("yap_forever.cli.remote.fetch_remote", lambda r, dest: calls.append(r) or 0):
            run_cli(["prices", "--remote", "--host", "  bob.test "], self.paths)
            code, out = run_cli(["prices", "--remote", "--host", "  "], self.paths)
        self.assertEqual(calls, [Remote("bob.test")])
        self.assertEqual(code, 1)
        self.assertIn("--host is empty", out)

    def test_host_flag_overrides_only_the_host(self):
        self.paths.remote.write_text('host = "file.test"\nkey = "/keys/k"\ncommand = "go"\n'
                                     'remote_file = "f.json"\n', encoding="utf-8")
        calls = []
        with mock.patch("yap_forever.cli.remote.fetch_remote", lambda r, dest: calls.append(r) or 0):
            run_cli(["prices", "--remote", "--host", "flag.test"], self.paths)
            run_cli(["prices", "--remote"], self.paths)
        self.assertEqual(calls, [Remote("flag.test", "/keys/k", "go", "f.json"),
                                 Remote("file.test", "/keys/k", "go", "f.json")])

    def test_bad_remote_toml_is_a_message(self):
        self.paths.remote.write_text('host = 5\n', encoding="utf-8")
        code, out = run_cli(["prices", "--remote"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("host", out)

    def test_exit_code_comes_from_the_fetch(self):
        with mock.patch("yap_forever.cli.remote.fetch_remote", lambda r, dest: 1):
            code, _ = run_cli(["prices", "--remote", "--host", "h.test"], self.paths)
        self.assertEqual(code, 1)

    def test_remote_and_auctionator_are_exclusive(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run_cli(["prices", "--remote", "--auctionator", "x.lua"], self.paths)

    def test_host_without_remote_is_refused(self):
        code, out = run_cli(["prices", "--host", "h.test"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("--remote", out)

    def test_realm_with_remote_is_refused(self):
        code, out = run_cli(["prices", "--remote", "--realm", "R"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("--auctionator", out)


if __name__ == "__main__":
    unittest.main()
