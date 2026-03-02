import pathlib
import sys

_HARNESS_DIR = pathlib.Path(__file__).parents[3] / "harness"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))
