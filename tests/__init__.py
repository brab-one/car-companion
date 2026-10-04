# Lets the tests import the companion package from python/.
# Run from the project folder:  python3 -m unittest
#
# The tests use their own copy of the shipped config (tests/fixtures/config),
# so what you change in config/ with the simulator does not break them.
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

CONFIG = ROOT / "tests" / "fixtures" / "config"
IMAGES = ["geisler.png", "schlern.png"]  # the shipped placeholders in assets/images
CLIPS = ["wheel.png"]                    # the shipped example clip in assets/clips


def make_project(folder):
    """config/, images/ and clips/ as shipped, in folder (a temporary directory)."""
    folder = Path(folder)
    shutil.copytree(CONFIG, folder / "config")
    for sub, names in (("images", IMAGES), ("clips", CLIPS)):
        (folder / sub).mkdir()
        for name in names:
            shutil.copy(ROOT / "assets" / sub / name, folder / sub)
