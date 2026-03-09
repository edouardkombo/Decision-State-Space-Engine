import json

from dsse import config as cfgmod


def test_try_load_config_ignores_legacy_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "APP_DIR", tmp_path)
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(cfgmod, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(cfgmod, "MODEL_DIR", tmp_path / "models")
    cfgmod.ensure_app_dirs()
    cfgmod.CONFIG_PATH.write_text(json.dumps({"model_name": "mistral-small", "model_path": "/old/path"}), encoding="utf-8")

    cfg, error = cfgmod.try_load_config()

    assert error is None
    assert cfg.model_name == "mistral-small"


def test_try_load_config_recovers_from_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "APP_DIR", tmp_path)
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(cfgmod, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(cfgmod, "MODEL_DIR", tmp_path / "models")
    cfgmod.ensure_app_dirs()
    cfgmod.CONFIG_PATH.write_text("{broken", encoding="utf-8")

    cfg, error = cfgmod.try_load_config()

    assert cfg.model_name is None
    assert error is not None
