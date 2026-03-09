from __future__ import annotations

import typer
from rich.console import Console

from dsse.config import save_session
from dsse.engine import DSSEEngine
from dsse.rendering import (
    show_business_case,
    show_current_mission,
    show_current_state,
    show_decision,
    show_event,
    show_header,
    show_paths,
    show_ranking,
    show_recent_changes,
)
from dsse.scenario_loader import load_case, load_event, load_route

console = Console()



def run_tutorial(case_key: str, route_name: str) -> None:
    try:
        route = load_route(case_key, route_name)
        case = load_case(case_key)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc

    engine = DSSEEngine(case)
    show_header(f"dsse tutorial run {case_key} --route {route_name}")
    console.print(f"Route\n{route.get('label', route_name)}\n")
    show_business_case(case)
    show_paths(case_key)
    show_current_mission(case, engine.current_ranking())
    show_current_state(case)
    show_ranking("Current factual ranking", engine.current_ranking())
    for event_key in route["events"]:
        event = load_event(case_key, event_key)
        deltas, notes = engine.apply_event(event)
        show_event(event, deltas, notes)
        show_recent_changes(case)
        show_current_mission(case, engine.current_ranking())
        show_ranking("Current ranking after new event", engine.current_ranking())
        show_decision(engine.recommend_action())
        if not typer.confirm("Continue tutorial?", default=True):
            break

    if route.get("expected_final_lifecycle"):
        console.print(f"Expected route lifecycle\n{route['expected_final_lifecycle']}")
        console.print(f"Observed lifecycle\n{case.lifecycle}\n")
    if route.get("expected_final_leader"):
        console.print(f"Expected route leader\n{route['expected_final_leader']}")
        console.print(f"Observed leader\n{engine.current_ranking()[0].provider}\n")
    save_session({"current_case": case_key, "route": route_name, "mode": "tutorial", "lifecycle": case.lifecycle, "history": case.history})
