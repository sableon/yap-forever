import os
import sys
import tempfile
from pathlib import Path

# The planner package lives in plugin/ (the folder players install). Put it first on the import
# path so `python3 -m unittest discover -s tests -t .` runs from the repository root as it is.
PLUGIN = Path(__file__).resolve().parent.parent / "plugin"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

# Keep every test away from the real player folder: anything that falls back to the
# default home lands in a throwaway directory instead.
os.environ["YAP_FOREVER_HOME"] = tempfile.mkdtemp(prefix="yap-forever-tests-")
