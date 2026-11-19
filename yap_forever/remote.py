"""Fetch prices through another machine over the system OpenSSH, when this one can't reach the API."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from yap_forever.prices import Market
from yap_forever.settings import Remote

NEEDS_OPENSSH = "remote fetch needs OpenSSH (ssh and scp) on your PATH"


def _step(run, name: str, argv: list[str]) -> bool:
    """Run one step; say which step failed (never the host or the command's output) and return False."""
    try:
        done = run(argv)
    except OSError:
        print(f"remote fetch failed: could not start {name}")
        return False
    if done.returncode != 0:
        print(f"remote fetch failed at the {name} step (exit code {done.returncode})")
        return False
    return True


def fetch_remote(remote: Remote, dest: Path, run=subprocess.run) -> int:
    """Run the remote command over ssh, copy its prices file back with scp, and replace `dest` with it
    only when it loads as a prices file. Returns an exit code."""
    if shutil.which("ssh") is None or shutil.which("scp") is None:
        print(NEEDS_OPENSSH)
        return 1
    if remote.host.startswith("-"):
        print("remote fetch: the host can't start with '-'")
        return 1
    key_args = ["-i", remote.key, "-o", "IdentitiesOnly=yes"] if remote.key else []
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if not _step(run, "ssh", ["ssh", *key_args, remote.host, remote.command]):
            return 1
        if not _step(run, "scp", ["scp", *key_args, f"{remote.host}:{remote.remote_file}", str(tmp)]):
            return 1
        try:
            m = Market.load(tmp)
        except ValueError:
            print("remote fetch: the prices file copied from the remote machine is damaged; "
                  "your saved prices are unchanged")
            return 1
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Saved {len(m.listings)} items from the remote machine, snapshot {m.snapshot_time or 'unknown'}.")
    return 0
