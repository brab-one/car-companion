# Lets the tests import the companion package from python/.
# Run from the project folder:  python3 -m unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
