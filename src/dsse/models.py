from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LifecycleStage = Literal[
    "draft", "active", "pending", "review", "blocked", "ready", "completed", "cancelled", "failed", "archived"
]


@dataclass(slots=True)
class ProviderOffer:
    name: str
    price: int
    term_months: int
    payment: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderMetrics:
    close_probability: float
    risk_adjusted_value: float
    blocker_burden: float
    uncertainty: float
    metric_drivers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RankingRow:
    provider: str
    offer: ProviderOffer
    metrics: ProviderMetrics
    rank: int = 0


@dataclass(slots=True)
class EventDelta:
    field: str
    before: Any
    after: Any


@dataclass(slots=True)
class CaseEvent:
    key: str
    title: str
    source_file: str
    provider: str | None
    deltas: list[EventDelta]
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExplanationPayload:
    action: str
    action_score: float
    expected_close_delta: float
    expected_blocker_reduction: float
    expected_risk_reduction: float
    autonomy_eligible: bool
    confidence: float
    reasons: list[str]


@dataclass(slots=True)
class SimulationProjection:
    key: str
    label: str
    target_provider: str | None
    projected_leader: str
    ranking: list[RankingRow]
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CaseState:
    case_key: str
    business_case: str
    business_need: str
    goal: str
    success_conditions: list[str]
    providers: dict[str, ProviderOffer]
    stakeholders: dict[str, list[str]]
    open_blockers: list[str]
    lifecycle: LifecycleStage = "active"
    status_reason: str = "case initialized"
    current_owner: str | None = None
    next_expected_action: str | None = None
    history: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)



def case_state_to_payload(case: CaseState) -> dict[str, Any]:
    return asdict(case)



def case_state_from_payload(payload: dict[str, Any]) -> CaseState:
    providers_payload = payload.get("providers") or {}
    providers = {
        name: ProviderOffer(
            name=(provider_payload or {}).get("name", name),
            price=int((provider_payload or {}).get("price", 0)),
            term_months=int((provider_payload or {}).get("term_months", 0)),
            payment=str((provider_payload or {}).get("payment", "")),
            strengths=list((provider_payload or {}).get("strengths", [])),
            weaknesses=list((provider_payload or {}).get("weaknesses", [])),
            metadata=dict((provider_payload or {}).get("metadata", {})),
        )
        for name, provider_payload in providers_payload.items()
    }
    return CaseState(
        case_key=str(payload["case_key"]),
        business_case=str(payload["business_case"]),
        business_need=str(payload["business_need"]),
        goal=str(payload["goal"]),
        success_conditions=list(payload.get("success_conditions", [])),
        providers=providers,
        stakeholders={str(k): list(v) for k, v in dict(payload.get("stakeholders", {})).items()},
        open_blockers=list(payload.get("open_blockers", [])),
        lifecycle=str(payload.get("lifecycle", "active")),
        status_reason=str(payload.get("status_reason", "case initialized")),
        current_owner=payload.get("current_owner"),
        next_expected_action=payload.get("next_expected_action"),
        history=list(payload.get("history", [])),
        signals=dict(payload.get("signals", {})),
    )
