"""Run the planner from any folder: <python> /path/to/plugin/yap-forever.py <command>.

The skill runs every command in this one form, so its allowed-tools rules can match it without
a `cd` first. Same as `python3 -m yap_forever <command>` run inside this folder.
Kept simple enough to run on an old Python and say which version is needed.
"""
import os
import runpy
import sys

if sys.version_info < (3, 11):
    sys.stdout.write("yap-forever needs Python 3.11 or newer; you have %d.%d.\n" % sys.version_info[:2])
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yap_forever import settings

settings.LAUNCHER = os.path.abspath(__file__)  # next-step hints name this command, not `-m yap_forever`
runpy.run_module("yap_forever", run_name="__main__", alter_sys=True)
