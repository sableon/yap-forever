"""Fetch prices through another machine over the system OpenSSH, when this one can't reach the API."""
import contextlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from yap_forever.prices import Market
from yap_forever.settings import Remote

NEEDS_OPENSSH = "remote fetch needs OpenSSH (ssh and scp) on your PATH"
SSH_TIMEOUT = 300  # seconds: the remote machine downloads the prices during this step
SCP_TIMEOUT = 120


def _step(run, name: str, argv: list[str], timeout: int, **kwargs) -> bool:
    """Run one step; say which step failed (never the host or the command's output) and return False."""
    try:
        done = run(argv, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        print(f"remote fetch failed at the {name} step (timed out after {timeout} seconds)")
        return False
    except OSError:
        print(f"remote fetch failed: could not start {name}")
        return False
    if done.returncode != 0:
        print(f"remote fetch failed at the {name} step (exit code {done.returncode})")
        return False
    return True


def fetch_remote(remote: Remote, dest: Path, run=subprocess.run, accept=None) -> int:
    """Run the remote command over ssh, copy its prices file back with scp, and replace `dest` with it
    only when it loads as a prices file with listings and `accept(market)` (when given) returns None;
    a returned string is why the copy is refused (it must not name the host). Returns an exit code."""
    if shutil.which("ssh") is None or shutil.which("scp") is None:
        print(NEEDS_OPENSSH)
        return 1
    host = remote.host.strip()
    if not host:
        print("remote fetch: the host is empty")
        return 1
    if host.startswith("-"):
        print("remote fetch: the host can't start with '-'")
        return 1
    # scp runs in dest's folder, so a key given as a relative path must be made absolute first
    # BatchMode: a passphrase or password prompt fails at once instead of hanging a script
    key_args = ["-o", "BatchMode=yes"]
    if remote.key:
        key_args += ["-i", os.path.abspath(remote.key), "-o", "IdentitiesOnly=yes"]
    dest = Path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
        os.close(fd)
    except OSError as e:
        print(f"remote fetch: can't write in {dest.parent}: {e.strerror or e}")
        return 1
    tmp = Path(tmp_name)
    try:
        if not _step(run, "ssh", ["ssh", *key_args, host, remote.command], SSH_TIMEOUT,
                     stdin=subprocess.DEVNULL):
            return 1
        # A bare file name and cwd: a Windows drive letter (C:\...) on the scp command line reads as a host.
        if not _step(run, "scp", ["scp", *key_args, f"{host}:{remote.remote_file}", tmp.name], SCP_TIMEOUT,
                     cwd=str(dest.parent)):
            return 1
        try:
            m = Market.load(tmp)
        except ValueError:
            print("remote fetch: the prices file copied from the remote machine is damaged; "
                  "your saved prices are unchanged")
            return 1
        if not m.listings:
            print("remote fetch: the prices file copied from the remote machine has no listings; "
                  "your saved prices are unchanged")
            return 1
        why = accept(m) if accept else None
        if why:
            print(f"remote fetch: {why}; your saved prices are unchanged")
            return 1
        try:
            os.replace(tmp, dest)
        except OSError as e:
            print(f"remote fetch: can't write {dest.name}: {e.strerror or e}")
            return 1
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
    print(f"Saved {len(m.listings)} items from the remote machine, snapshot {m.snapshot_time or 'unknown'}.")
    return 0
