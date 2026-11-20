"""plugin/yap-forever.py: the one command form the skill runs, from any folder."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from yap_forever.__main__ import python_too_old

LAUNCHER = Path(__file__).resolve().parent.parent / "plugin" / "yap-forever.py"


class LauncherTests(unittest.TestCase):
    def test_runs_a_command_from_another_folder(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            env = dict(os.environ, YAP_FOREVER_HOME=str(home))
            env.pop("PYTHONPATH", None)
            r = subprocess.run([sys.executable, str(LAUNCHER), "init"], cwd=d, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            self.assertTrue((home / "profile.toml").exists())

    def test_passes_the_exit_code_on(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, YAP_FOREVER_HOME=str(Path(d) / "empty"))
            r = subprocess.run([sys.executable, str(LAUNCHER), "check", "--offline"], cwd=d, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 1)
            self.assertIn("profile", r.stdout)

    def test_old_python_message_is_the_packages(self):
        """The launcher checks the version before importing anything; its message is the same."""
        source = LAUNCHER.read_text(encoding="utf-8")
        template = re.search(r'sys\.stdout\.write\("(.*?)\\n"', source).group(1)
        self.assertEqual(template % (3, 9), python_too_old((3, 9)))
        self.assertIn("(3, 11)", source)


if __name__ == "__main__":
    unittest.main()
