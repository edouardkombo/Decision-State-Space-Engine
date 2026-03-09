from __future__ import annotations

import typer
from rich.console import Console

from dsse.config import AppConfig, clear_local_state, save_config, save_session, try_load_config
from dsse.db import DatabaseManager
from dsse.engine import DSSEEngine, SIMULATION_META
from dsse.models import CaseState
from dsse.rendering import (
    show_active_strategy,
    show_business_case,
    show_current_mission,
    show_current_state,
    show_decision,
    show_event,
    show_header,
    show_next_menu,
    show_commit_ack,
    show_paths,
    show_projection,
    show_ranking,
    show_recent_changes,
)
from dsse.scenario_loader import list_cases, list_event_names, list_route_names, load_case, load_event
from dsse.setup_manager import run_interactive_setup
from dsse.storage import DATA_DIR
from dsse.tutorial import run_tutorial

app = typer.Typer(help="Decision State Space Engine")
case_app = typer.Typer(help="Run and inspect negotiation cases")
tutorial_app = typer.Typer(help="Run tutorial routes")
app.add_typer(case_app, name="case")
app.add_typer(tutorial_app, name="tutorial")
console = Console()

SIMULATION_OPTIONS = list(SIMULATION_META.items())


def _load_cfg_or_exit() -> AppConfig:
    cfg, err = try_load_config()
    if err:
        console.print(err)
        console.print("Run [bold]dsse reset[/bold] to clear broken local state, or repair the JSON file manually.")
        raise typer.Exit(code=1)
    return cfg



def _require_setup(cfg: AppConfig) -> None:
    if not cfg.model_name or not cfg.postgres_dsn:
        console.print("Setup not complete. Run [bold]dsse setup[/bold] first.")
        raise typer.Exit(code=1)



def _prompt_index(prompt: str, size: int) -> int:
    while True:
        choice = typer.prompt(prompt, type=int)
        if 1 <= choice <= size:
            return choice - 1
        console.print(f"Select a number between 1 and {size}.")



def _load_case_or_exit(case_key: str) -> CaseState:
    try:
        return load_case(case_key)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc



def _load_event_or_exit(case_key: str, event_key: str):
    try:
        return load_event(case_key, event_key)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc



def _db_manager(cfg: AppConfig) -> DatabaseManager:
    return DatabaseManager(cfg.postgres_dsn or "")



def _persist_live_session(case_key: str, case: CaseState) -> None:
    save_session(
        {
            "current_case": case_key,
            "mode": "live",
            "lifecycle": case.lifecycle,
            "status_reason": case.status_reason,
            "current_owner": case.current_owner,
            "next_expected_action": case.next_expected_action,
            "history": list(case.history),
            "signals": dict(case.signals),
        }
    )



def _persist_runtime_or_exit(cfg: AppConfig, case: CaseState, event_type: str, payload: dict | None = None) -> None:
    result = _db_manager(cfg).save_case_runtime(case, event_type, payload)
    if not result.ok:
        console.print(result.message)
        console.print("Runtime state was not persisted, so DSSE stopped rather than pretending PostgreSQL is the source of truth.")
        raise typer.Exit(code=1)
    _persist_live_session(case.case_key, case)



def _resolve_live_case(cfg: AppConfig, case_key: str, initialize_if_missing: bool = True) -> tuple[CaseState, str]:
    db = _db_manager(cfg)
    try:
        runtime_case = db.load_case_runtime(case_key)
    except RuntimeError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc

    if runtime_case is not None:
        return runtime_case, "postgresql"

    baseline_case = _load_case_or_exit(case_key)
    if initialize_if_missing:
        _persist_runtime_or_exit(cfg, baseline_case, "case_initialized", {"origin": "baseline"})
        return baseline_case, "postgresql"
    return baseline_case, "baseline"



def _start_case_session(cfg: AppConfig, case_key: str) -> tuple[CaseState, str]:
    case, source = _resolve_live_case(cfg, case_key, initialize_if_missing=True)
    cfg.current_case = case_key
    save_config(cfg)
    _persist_live_session(case_key, case)
    return case, source



def _choose_case_interactively(default_case: str | None = None) -> str | None:
    cases = list_cases()
    if not cases:
        console.print("No bundled cases found.")
        return None

    if default_case and default_case in cases:
        console.print(f"Default case\n{default_case}\n")
        if typer.confirm("Use this case?", default=True):
            return default_case

    console.print("Available cases\n")
    for idx, case_key in enumerate(cases, start=1):
        console.print(f"{idx}) {case_key}")
    selected = _prompt_index("Select case", len(cases))
    return cases[selected]



def _show_case_state(case_key: str, case: CaseState, engine: DSSEEngine, state_source: str, refreshed: bool = False, first_view: bool = False) -> None:
    ranking = engine.current_ranking()
    show_header(f"dsse case run {case_key}")
    if refreshed:
        console.print("Interactive state refreshed\n")
    console.print(f"State source\n{state_source}\n")
    console.print(f"Case status\n{case.lifecycle}\n")
    console.print(f"Reason\n{case.status_reason}\n")
    if case.current_owner:
        console.print(f"Current owner\n{case.current_owner}\n")
    if case.next_expected_action:
        console.print(f"Next expected action\n{case.next_expected_action}\n")

    if first_view:
        show_business_case(case)
        show_paths(case_key)

    show_current_mission(case, ranking)
    show_recent_changes(case)
    show_active_strategy(case)
    show_current_state(case)
    show_ranking("Current factual ranking", ranking)
    show_decision(engine.recommend_action())
    show_next_menu(case)



def _run_case_loop(case_key: str, cfg: AppConfig) -> None:
    case, source = _start_case_session(cfg, case_key)
    engine = DSSEEngine(case)
    refreshed = False
    first_view = True

    while True:
        _show_case_state(case_key, case, engine, state_source=source, refreshed=refreshed, first_view=first_view)
        refreshed = False
        first_view = False
        choice = _prompt_index("Choose", 6) + 1

        if choice == 1:
            existing_plan = case.signals.get("active_plan")
            existing_label = existing_plan.get("label") if isinstance(existing_plan, dict) and not existing_plan.get("stale") else None
            payload = engine.accept_recommendation()
            already_committed = existing_label == payload.action
            if already_committed:
                console.print(f"Already committed\n{payload.action}\n")
            else:
                console.print(f"Accepted\n{payload.action}\n")
                _persist_runtime_or_exit(cfg, case, "recommendation_accepted", {"action": payload.action})
                source = "postgresql"
            show_commit_ack(case, payload, already_committed=already_committed)
            terminal_lifecycles = {"completed", "cancelled", "failed", "archived"}
            if case.lifecycle in terminal_lifecycles:
                console.print("Interactive run closed because the case reached a terminal lifecycle.\n")
                break
            if typer.confirm("Close interactive run now?", default=True):
                break
            refreshed = True
            continue
        elif choice == 2:
            payload = engine.recommend_action()
            console.print("Action math\n")
            console.print(f"Winning action score:            {payload.action_score}")
            console.print(f"Expected close delta:            +{payload.expected_close_delta:.2f}")
            console.print(f"Expected blocker reduction:      -{payload.expected_blocker_reduction:.2f}")
            console.print(f"Expected risk reduction:         -{payload.expected_risk_reduction:.2f}")
            console.print(f"Confidence:                      {payload.confidence}")
        elif choice == 3:
            console.print("Simulate alternative\n")
            for idx, (_key, (label, _target)) in enumerate(SIMULATION_OPTIONS, start=1):
                console.print(f"{idx}. {label}")
            selected = _prompt_index("Choose simulation", len(SIMULATION_OPTIONS))
            simulation_key, (label, _target) = SIMULATION_OPTIONS[selected]
            projection = engine.simulate_alternative(simulation_key)
            show_projection(f"Projected effect for '{label}'", projection)
            if typer.confirm("Set this as the active strategy branch?", default=False):
                engine.set_active_branch(projection)
                _persist_runtime_or_exit(
                    cfg,
                    case,
                    "strategy_branch_selected",
                    {
                        "branch_key": projection.key,
                        "branch_label": projection.label,
                        "target_provider": projection.target_provider,
                        "projected_leader": projection.projected_leader,
                    },
                )
                source = "postgresql"
                refreshed = True
        elif choice == 4:
            override = typer.prompt("Type override action")
            engine.set_manual_override(override)
            _persist_runtime_or_exit(cfg, case, "manual_override", {"action": override})
            source = "postgresql"
            console.print(f"Override stored\n{override}")
            refreshed = True
        elif choice == 5:
            try:
                available = list_event_names(case_key)
            except FileNotFoundError as exc:
                raise typer.BadParameter(str(exc)) from exc
            if not available:
                console.print("No sample events found for this case.")
                continue
            console.print("Available sample events\n")
            for idx, event_name in enumerate(available, start=1):
                console.print(f"{idx}. {event_name}")
            ev_idx = _prompt_index("Select event", len(available))
            event = _load_event_or_exit(case_key, available[ev_idx])
            before = engine.current_ranking()
            deltas, notes = engine.apply_event(event)
            _persist_runtime_or_exit(cfg, case, "factual_event_ingested", {"event_key": event.key, "event_title": event.title})
            source = "postgresql"
            show_event(event, deltas, notes)
            after = engine.current_ranking()
            console.print("Metric update\n")
            console.print(f"Leader before: {before[0].provider}")
            console.print(f"Leader after:  {after[0].provider}\n")
            show_ranking("Current ranking after new event", after)
            refreshed = True
        else:
            break
        if choice != 6 and not typer.confirm("Continue interactive run?", default=True):
            break


@app.command()
def setup() -> None:
    show_header("dsse setup", "Decision State Space Engine\nEnvironment setup")
    cfg = run_interactive_setup(seed_case=True)
    console.print("\nSetup complete")
    console.print(f"Current model\n{cfg.model_name}")
    console.print(f"Database\n{cfg.postgres_dsn}")
    default_case = "strategic-multi-lane-deadlock" if cfg.case_seeded else None
    if cfg.case_seeded:
        console.print("Bundled sample case available\nstrategic-multi-lane-deadlock")

    console.print("")
    if not typer.confirm("Launch interactive case now?", default=True):
        return

    case_key = _choose_case_interactively(default_case=default_case)
    if not case_key:
        console.print("No case was available to launch.")
        return

    console.print(f"\nStarting interactive case\n{case_key}\n")
    _run_case_loop(case_key, cfg)


@app.command()
def reset(local_only: bool = typer.Option(False, help="Clear only local DSSE files under ~/.dsse and skip database reset.")) -> None:
    cfg, cfg_error = try_load_config()
    show_header("dsse reset", "Decision State Space Engine\nReset")
    if cfg_error:
        console.print(f"Configuration warning\n{cfg_error}\n")
    console.print("This can delete DSSE database state and local session state.\n")
    confirm = typer.prompt("Type YES to continue")
    if confirm != "YES":
        console.print("Reset cancelled")
        raise typer.Exit()

    if local_only:
        clear_local_state()
        console.print("Local configuration cleared")
        return

    if cfg.postgres_dsn:
        db = DatabaseManager(cfg.postgres_dsn)
        result = db.reset_database()
        console.print(result.message)
        if not result.ok:
            console.print("Local files were kept because the database reset failed.")
            raise typer.Exit(code=1)
        clear_local_state()
        console.print("Local configuration cleared")
        return

    console.print("No valid PostgreSQL DSN was available, so only local DSSE files were cleared.")
    clear_local_state()
    console.print("Local configuration cleared")


@case_app.command("list")
def case_list() -> None:
    show_header("dsse case list")
    console.print(f"Case data root\n{DATA_DIR}\n")
    console.print("Available cases\n")
    cases = list_cases()
    if not cases:
        console.print("No bundled cases found.")
        raise typer.Exit(code=1)
    for case_key in cases:
        console.print(f"- {case_key}")


@case_app.command("start")
def case_start(case_key: str) -> None:
    cfg = _load_cfg_or_exit()
    _require_setup(cfg)
    show_header(f"dsse case start {case_key}")
    case, source = _start_case_session(cfg, case_key)
    console.print(f"Case started\n{case_key}")
    console.print(f"Lifecycle\n{case.lifecycle}")
    console.print(f"State source\n{source}")


@case_app.command("status")
def case_status(case_key: str) -> None:
    cfg = _load_cfg_or_exit()
    _require_setup(cfg)
    case, source = _resolve_live_case(cfg, case_key, initialize_if_missing=False)
    engine = DSSEEngine(case)
    show_header(f"dsse case status {case_key}")
    console.print(f"State source\n{source}\n")
    console.print("Case status")
    console.print(case.lifecycle)
    console.print(f"\nReason\n{case.status_reason}\n")
    show_business_case(case)
    show_current_mission(case, engine.current_ranking())
    show_recent_changes(case)
    show_active_strategy(case)
    show_current_state(case)
    show_ranking("Current factual ranking", engine.current_ranking())


@case_app.command("run")
def case_run(case_key: str) -> None:
    cfg = _load_cfg_or_exit()
    _require_setup(cfg)
    _run_case_loop(case_key, cfg)


@tutorial_app.command("run")
def tutorial_run(case_key: str, route: str = typer.Option(..., help="Route name used only for tutorial, replay, or QA")) -> None:
    cfg = _load_cfg_or_exit()
    _require_setup(cfg)
    run_tutorial(case_key, route)


@tutorial_app.command("routes")
def tutorial_routes(case_key: str) -> None:
    show_header(f"dsse tutorial routes {case_key}")
    console.print("Available routes\n")
    routes = list_route_names(case_key)
    if not routes:
        console.print("No routes found for this case.")
        raise typer.Exit(code=1)
    for route in routes:
        console.print(f"- {route}")


if __name__ == "__main__":
    app()
