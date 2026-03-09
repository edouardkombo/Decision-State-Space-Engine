from __future__ import annotations

from pathlib import Path

from dsse.models import CaseEvent, CaseState, EventDelta, ProviderOffer
from dsse.storage import DATA_DIR, case_dir, read_json


def list_cases() -> list[str]:
    if not DATA_DIR.exists():
        return []
    return sorted([p.name for p in DATA_DIR.iterdir() if p.is_dir()])


def load_case(case_key: str) -> CaseState:
    cdir = case_dir(case_key)
    case_meta = read_json(cdir / "case.json")
    providers_json = read_json(cdir / "baseline" / "providers.json")
    stakeholders_json = read_json(cdir / "baseline" / "stakeholders.json")
    constraints_json = read_json(cdir / "baseline" / "constraints.json")

    providers = {
        item["name"]: ProviderOffer(
            name=item["name"],
            price=item["price"],
            term_months=item["term_months"],
            payment=item["payment"],
            strengths=item.get("strengths", []),
            weaknesses=item.get("weaknesses", []),
            metadata=item.get("metadata", {}),
        )
        for item in providers_json["providers"]
    }

    return CaseState(
        case_key=case_key,
        business_case=case_meta["business_case"],
        business_need=case_meta["business_need"],
        goal=case_meta["goal"],
        success_conditions=case_meta["success_conditions"],
        providers=providers,
        stakeholders=stakeholders_json["stakeholders"],
        open_blockers=constraints_json["open_blockers"],
        lifecycle="active",
        status_reason="case initialized",
        signals={"deadline_days": 45},
    )


def list_event_names(case_key: str) -> list[str]:
    events_dir = case_dir(case_key) / "artifacts" / "events"
    if not events_dir.exists():
        raise FileNotFoundError(f"No events directory found for case '{case_key}': {events_dir}")
    return sorted(p.stem for p in events_dir.glob("*.json"))


def load_event(case_key: str, event_key: str) -> CaseEvent:
    cdir = case_dir(case_key)
    payload = read_json(cdir / "artifacts" / "events" / f"{event_key}.json")
    deltas = [EventDelta(field=d["field"], before=d["before"], after=d["after"]) for d in payload["deltas"]]
    return CaseEvent(
        key=payload["key"],
        title=payload["title"],
        source_file=payload["source_file"],
        provider=payload.get("provider"),
        deltas=deltas,
        notes=payload.get("notes", []),
    )


def list_route_names(case_key: str) -> list[str]:
    cdir = case_dir(case_key) / "routes"
    if not cdir.exists():
        return []
    return sorted([p.stem for p in cdir.glob("*.json")])


def load_route(case_key: str, route_name: str) -> dict:
    return read_json(case_dir(case_key) / "routes" / f"{route_name}.json")
