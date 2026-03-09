import json
from pathlib import Path

from typer.testing import CliRunner

from dsse import cli as cli_mod
from dsse import config as config_mod
from dsse.db import DatabaseCheck

runner = CliRunner()


def _patch_paths(monkeypatch, tmp_path: Path):
    app_dir = tmp_path / '.dsse'
    monkeypatch.setattr(config_mod, 'APP_DIR', app_dir)
    monkeypatch.setattr(config_mod, 'CONFIG_PATH', app_dir / 'config.json')
    monkeypatch.setattr(config_mod, 'SESSION_PATH', app_dir / 'session.json')
    monkeypatch.setattr(config_mod, 'MODEL_DIR', app_dir / 'models')
    return app_dir


class FailingDB:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def reset_database(self):
        return DatabaseCheck(False, 'Reset failed: boom')


def test_reset_clears_broken_local_state(monkeypatch, tmp_path):
    app_dir = _patch_paths(monkeypatch, tmp_path)
    app_dir.mkdir(parents=True)
    config_mod.CONFIG_PATH.write_text('{broken json', encoding='utf-8')

    result = runner.invoke(cli_mod.app, ['reset'], input='YES\n')

    assert result.exit_code == 0
    assert 'only local DSSE files were cleared' in result.stdout
    assert not config_mod.CONFIG_PATH.exists()


def test_reset_keeps_local_files_when_db_reset_fails(monkeypatch, tmp_path):
    app_dir = _patch_paths(monkeypatch, tmp_path)
    app_dir.mkdir(parents=True)
    config_mod.CONFIG_PATH.write_text(json.dumps({
        'model_name': 'mistral-small',
        'postgres_dsn': 'postgresql://user:pass@localhost:5432/dsse'
    }), encoding='utf-8')
    monkeypatch.setattr(cli_mod, 'DatabaseManager', FailingDB)

    result = runner.invoke(cli_mod.app, ['reset'], input='YES\n')

    assert result.exit_code == 1
    assert 'Local files were kept because the database reset failed.' in result.stdout
    assert config_mod.CONFIG_PATH.exists()


def test_case_start_unknown_case_returns_friendly_error(monkeypatch, tmp_path):
    app_dir = _patch_paths(monkeypatch, tmp_path)
    app_dir.mkdir(parents=True)
    config_mod.CONFIG_PATH.write_text(json.dumps({
        'model_name': 'mistral-small',
        'postgres_dsn': 'postgresql://user:pass@localhost:5432/dsse'
    }), encoding='utf-8')

    result = runner.invoke(cli_mod.app, ['case', 'start', 'missing-case'])

    assert result.exit_code != 0
    assert "Case 'missing-case' was not found" in result.stdout
