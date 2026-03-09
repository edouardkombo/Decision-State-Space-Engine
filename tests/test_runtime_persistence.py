from types import SimpleNamespace

import pytest
from click.exceptions import Exit

from dsse import cli
from dsse.config import AppConfig
from dsse.models import CaseState, case_state_from_payload, case_state_to_payload
from dsse.scenario_loader import load_case


class FakeDB:
    store: dict[str, CaseState] = {}
    saved: list[tuple[str, str, dict | None]] = []

    def __init__(self, dsn: str):
        self.dsn = dsn

    def load_case_runtime(self, case_key: str):
        return self.store.get(case_key)

    def save_case_runtime(self, case: CaseState, event_type: str, payload: dict | None = None):
        cloned = case_state_from_payload(case_state_to_payload(case))
        self.store[case.case_key] = cloned
        self.saved.append((case.case_key, event_type, payload))
        return SimpleNamespace(ok=True, message="ok")


class FailingDB(FakeDB):
    def save_case_runtime(self, case: CaseState, event_type: str, payload: dict | None = None):
        return SimpleNamespace(ok=False, message="boom")


@pytest.fixture(autouse=True)
def _reset_fake_db():
    FakeDB.store = {}
    FakeDB.saved = []
    yield



def test_case_state_payload_roundtrip_preserves_signals_and_offers():
    case = load_case("strategic-multi-lane-deadlock")
    case.signals["deadline_days"] = 30
    case.signals["active_plan"] = {"label": "Prepare close on CoreDesk", "stale": False}
    case.providers["CoreDesk"].strengths.append("delivery validation completed")
    payload = case_state_to_payload(case)
    restored = case_state_from_payload(payload)
    assert restored.case_key == case.case_key
    assert restored.signals["deadline_days"] == 30
    assert restored.signals["active_plan"]["label"] == "Prepare close on CoreDesk"
    assert "delivery validation completed" in restored.providers["CoreDesk"].strengths



def test_resolve_live_case_initializes_from_baseline_then_resumes_from_runtime(monkeypatch):
    monkeypatch.setattr(cli, "DatabaseManager", FakeDB)
    cfg = AppConfig(model_name="mistral-small", postgres_dsn="postgresql://postgres:password@localhost:5432/dsse")

    first_case, first_source = cli._resolve_live_case(cfg, "strategic-multi-lane-deadlock", initialize_if_missing=True)
    assert first_source == "baseline"
    assert FakeDB.saved[0][1] == "case_initialized"

    first_case.status_reason = "mutated in runtime"
    cli._persist_runtime_or_exit(cfg, first_case, "manual_override", {"action": "do something"})

    second_case, second_source = cli._resolve_live_case(cfg, "strategic-multi-lane-deadlock", initialize_if_missing=True)
    assert second_source == "postgresql"
    assert second_case.status_reason == "mutated in runtime"



def test_persist_runtime_or_exit_stops_when_database_write_fails(monkeypatch):
    monkeypatch.setattr(cli, "DatabaseManager", FailingDB)
    cfg = AppConfig(model_name="mistral-small", postgres_dsn="postgresql://postgres:password@localhost:5432/dsse")
    case = load_case("strategic-multi-lane-deadlock")
    with pytest.raises(Exit):
        cli._persist_runtime_or_exit(cfg, case, "case_initialized", {"origin": "baseline"})
