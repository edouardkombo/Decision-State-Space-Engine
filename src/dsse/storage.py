from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent


def _candidate_data_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_data = os.getenv("DSSE_DATA_DIR")
    if env_data:
        candidates.append(Path(env_data).expanduser())
    candidates.extend([
        PACKAGE_ROOT / "data" / "cases",
        ROOT / "data" / "cases",
    ])
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(candidate)
    return deduped



def _looks_like_case_root(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    case_dirs = [p for p in path.iterdir() if p.is_dir()]
    if not case_dirs:
        return False
    for case_path in case_dirs:
        if (case_path / "case.json").exists() and (case_path / "baseline" / "providers.json").exists():
            return True
    return False



def discover_data_dir() -> Path:
    for candidate in _candidate_data_dirs():
        if _looks_like_case_root(candidate):
            return candidate
    searched = "\n".join(str(p) for p in _candidate_data_dirs())
    raise FileNotFoundError(f"DSSE case data directory not found. Searched:\n{searched}")


DATA_DIR = discover_data_dir()



def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))



def case_dir(case_key: str) -> Path:
    path = DATA_DIR / case_key
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Unknown case '{case_key}'. Expected directory: {path}")
    return path
