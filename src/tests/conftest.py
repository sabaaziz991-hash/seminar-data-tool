"""Test setup: everything the tool writes during tests goes to a temporary folder (never into the project),
and temporary folders created by the tests are removed at the end of the session."""
import atexit
import glob
import os
import shutil
import sys
import tempfile
from pathlib import Path

_OUT = tempfile.mkdtemp(prefix="sdt_test_out_")
os.environ.setdefault("SEMINAR_TOOL_OUTPUT", _OUT)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@atexit.register
def _cleanup() -> None:
    shutil.rmtree(_OUT, ignore_errors=True)
    for d in glob.glob(os.path.join(tempfile.gettempdir(), "sdt_*")):
        shutil.rmtree(d, ignore_errors=True)
