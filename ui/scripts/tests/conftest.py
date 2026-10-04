import sys
from pathlib import Path

UI = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(UI / "scripts"))
sys.path.insert(0, str(UI / "server"))
sys.path.insert(0, str(UI.parent))
