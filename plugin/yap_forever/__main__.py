"""python3 -m yap_forever <command>: see cli.py. Checks the Python version before anything else."""
from __future__ import annotations  # keeps this file importable on old Pythons

import sys


def python_too_old(version: tuple[int, int]) -> str | None:
    if tuple(version) >= (3, 11):
        return None
    return f"yap-forever needs Python 3.11 or newer; you have {version[0]}.{version[1]}."


if __name__ == "__main__":
    message = python_too_old(sys.version_info[:2])
    if message:
        print(message)
        sys.exit(1)
    # A console in a legacy code page (Windows pipes) can't show every path: escape what it can't.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    from yap_forever import cli
    sys.exit(cli.main(sys.argv[1:]))
