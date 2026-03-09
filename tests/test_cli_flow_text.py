from dsse.engine import DSSEEngine
from dsse.models import CaseState, ProviderOffer
from dsse.rendering import _decision_frame, _mission_statement


def make_case():
    providers = {
        "CoreDesk": ProviderOffer(name="CoreDesk", price=129000, term_months=24, payment="net 30", strengths=["cooperative legal posture"], weaknesses=["implementation capacity uncertain"]),
        "AlphaSoft": ProviderOffer(name="AlphaSoft", price=148000, term_months=36, payment="annual upfront", strengths=["strongest implementation team"], weaknesses=["finance resistance to annual upfront"]),
    }
    return CaseState(
        case_key="x",
        business_case="b",
        business_need="n",
        goal="g",
        success_conditions=["s"],
        providers=providers,
        stakeholders={},
        open_blockers=["AlphaSoft finance blocker on annual prepay"],
    )


def test_committed_plan_changes_mission_and_frame():
    case = make_case()
    engine = DSSEEngine(case)
    payload = engine.accept_recommendation()
    assert payload.action.startswith("Prepare close on")
    statement = _mission_statement(case, "CoreDesk", 45)
    frame = _decision_frame(case, engine.current_ranking())
    assert "Execute 'Prepare close on" in statement
    assert "execute the committed lane" in frame
