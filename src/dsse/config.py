from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_DIR = Path.home() / ".dsse"
CONFIG_PATH = APP_DIR / "config.json"
SESSION_PATH = APP_DIR / "session.json"
MODEL_DIR = APP_DIR / "models"


@dataclass(slots=True)
class AppConfig:
    model_name: str | None = None
    model_source: str | None = None
    postgres_dsn: str | None = None
    use_pgvector: bool = False
    case_seeded: bool = False
    current_case: str | None = None


def ensure_app_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


_ALLOWED_KEYS = {f.name for f in fields(AppConfig)}


def _coerce_config_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Config payload must be a JSON object.")
    cleaned = {key: value for key, value in payload.items() if key in _ALLOWED_KEYS}
    return cleaned


def try_load_config() -> tuple[AppConfig, str | None]:
    ensure_app_dirs()
    if not CONFIG_PATH.exists():
        return AppConfig(), None
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AppConfig(**_coerce_config_payload(payload)), None
    except Exception as exc:
        return AppConfig(), f"Could not read DSSE config at {CONFIG_PATH}: {exc}"


def load_config() -> AppConfig:
    cfg, error = try_load_config()
    if error:
        raise ValueError(error)
    return cfg


def save_config(cfg: AppConfig) -> None:
    ensure_app_dirs()
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def save_session(payload: dict) -> None:
    ensure_app_dirs()
    SESSION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session() -> dict:
    ensure_app_dirs()
    if not SESSION_PATH.exists():
        return {}
    try:
        payload = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def clear_local_state() -> None:
    for p in (CONFIG_PATH, SESSION_PATH):
        if p.exists():
            p.unlink()
