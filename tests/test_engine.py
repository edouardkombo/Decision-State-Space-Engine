from dsse.engine import DSSEEngine
from dsse.scenario_loader import load_case, load_event, load_route


def test_event_changes_offer_price():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    event = load_event("strategic-multi-lane-deadlock", "012_alpha_v2_reply")
    engine.apply_event(event)
    assert case.providers["AlphaSoft"].price == 136000



def test_recommend_action_returns_payload():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    payload = engine.recommend_action()
    assert payload.action
    assert payload.action_score > 0



def test_global_deadline_event_updates_signal_and_history():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    event = load_event("strategic-multi-lane-deadlock", "010_requester_deadline_change")
    engine.apply_event(event)
    assert case.signals["deadline_days"] == 30
    assert event.key in case.history



def test_alpha_close_route_makes_alphasoft_lead():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    route = load_route("strategic-multi-lane-deadlock", "alpha_close")
    for event_key in route["events"]:
        engine.apply_event(load_event("strategic-multi-lane-deadlock", event_key))
    assert engine.current_ranking()[0].provider == "AlphaSoft"



def test_validate_coredesk_delivery_simulation_improves_coredesk_probability():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    baseline = next(row for row in engine.current_ranking() if row.provider == "CoreDesk")
    projection = engine.simulate_alternative("validate_coredesk_delivery_now")
    projected_row = next(row for row in projection.ranking if row.provider == "CoreDesk")
    assert projection.projected_leader == "CoreDesk"
    assert projected_row.metrics.close_probability >= baseline.metrics.close_probability
    assert projection.notes



def test_setting_active_branch_keeps_factual_ranking_unbiased_until_real_event():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    baseline_leader = engine.current_ranking()[0].provider
    projection = engine.simulate_alternative("push_finance_now")
    engine.set_active_branch(projection)
    assert case.signals["active_branch"]["target_provider"] == "AlphaSoft"
    assert engine.current_ranking()[0].provider == baseline_leader



def test_real_event_marks_active_branch_stale():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    projection = engine.simulate_alternative("push_finance_now")
    engine.set_active_branch(projection)
    engine.apply_event(load_event("strategic-multi-lane-deadlock", "010_requester_deadline_change"))
    assert case.signals["active_branch"]["stale"] is True


def test_committing_conflicting_action_marks_branch_stale():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    projection = engine.simulate_alternative("push_finance_now")
    engine.set_active_branch(projection)
    engine.accept_recommendation()
    assert case.signals["active_branch"]["stale"] is True
    assert "committed action moved to CoreDesk" in case.signals["active_branch"]["stale_reason"]


def test_real_event_marks_active_plan_stale():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    engine.accept_recommendation()
    engine.apply_event(load_event("strategic-multi-lane-deadlock", "010_requester_deadline_change"))
    assert case.signals["active_plan"]["stale"] is True


def test_reaccepting_same_plan_does_not_change_next_expected_action():
    case = load_case("strategic-multi-lane-deadlock")
    engine = DSSEEngine(case)
    first = engine.accept_recommendation()
    next_expected = case.next_expected_action
    second = engine.accept_recommendation()
    assert first.action == second.action
    assert case.next_expected_action == next_expected
