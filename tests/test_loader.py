import pytest

from dsse.scenario_loader import load_case, load_event, list_event_names, list_route_names
from dsse.storage import _looks_like_case_root


def test_case_loads():
    case = load_case("strategic-multi-lane-deadlock")
    assert case.case_key == "strategic-multi-lane-deadlock"
    assert "AlphaSoft" in case.providers



def test_event_loads():
    event = load_event("strategic-multi-lane-deadlock", "012_alpha_v2_reply")
    assert event.provider == "AlphaSoft"
    assert event.deltas



def test_routes_present():
    routes = list_route_names("strategic-multi-lane-deadlock")
    assert "alpha_close" in routes



def test_event_names_present():
    events = list_event_names("strategic-multi-lane-deadlock")
    assert "010_requester_deadline_change" in events



def test_missing_case_raises_clean_error():
    with pytest.raises(FileNotFoundError):
        load_case("missing-case")



def test_data_root_validator_rejects_partial_case_tree(tmp_path):
    partial_root = tmp_path / "data" / "cases"
    partial_case = partial_root / "strategic-multi-lane-deadlock"
    partial_case.mkdir(parents=True)
    assert _looks_like_case_root(partial_root) is False
