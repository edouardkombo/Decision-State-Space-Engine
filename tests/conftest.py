from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DSSE_DATA_DIR", str(ROOT / "src" / "dsse" / "data" / "cases"))
