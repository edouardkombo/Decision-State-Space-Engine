from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dsse.models import CaseEvent, CaseState, ExplanationPayload, RankingRow, SimulationProjection

console = Console()


def show_header(command: str, title: str = "Decision State Space Engine\nNegotiation Pack") -> None:
    console.print(Panel(title, title="DSSE", expand=False))
    console.print(f"Ran command\n> {command}\n")



def show_business_case(case: CaseState) -> None:
    console.print("[bold]Case identity[/bold]")
    console.print(f"Business case\n{case.business_case}\n")
    console.print("Original business need")
    console.print(case.business_need)
    console.print("\nOriginal goal")
    console.print(case.goal)
    console.print("\nOriginal success conditions")
    for item in case.success_conditions:
        console.print(f"- {item}")
    console.print()



def _dominant_risk(case: CaseState, ranking: list[RankingRow]) -> str:
    if int(case.signals.get("deadline_days", 45) or 45) <= 30:
        return "deadline pressure makes execution certainty more valuable than small commercial gains"
    if ranking and ranking[0].metrics.blocker_burden >= 0.3:
        return "blocker burden is still too high on the leading lanes"
    if any("security" in b.lower() for b in case.open_blockers):
        return "security ambiguity can still kill the cheapest lane"
    return "provider selection still depends on resolving the strongest remaining blocker"



def _decision_frame(case: CaseState, ranking: list[RankingRow]) -> str:
    active_plan = case.signals.get("active_plan")
    if isinstance(active_plan, dict) and not active_plan.get("stale") and active_plan.get("target_provider"):
        return f"execute the committed lane on {active_plan['target_provider']} until new evidence invalidates it"
    if int(case.signals.get("deadline_days", 45) or 45) <= 30:
        return "bias toward implementation safety and fast mobilization"
    if ranking and ranking[0].provider == "AlphaSoft":
        return "strong execution can justify a premium if blockers truly clear"
    return "keep price discipline without sacrificing readiness"



def _mission_statement(case: CaseState, leader: str, deadline_days: int) -> str:
    active_plan = case.signals.get("active_plan")
    if isinstance(active_plan, dict) and not active_plan.get("stale") and active_plan.get("label"):
        return f"Execute '{active_plan['label']}' inside {deadline_days} days and gather confirming or disconfirming evidence before changing lane."
    return f"Secure the safest implementation-ready path inside {deadline_days} days while keeping the live leader honest."



def show_current_mission(case: CaseState, ranking: list[RankingRow]) -> None:
    leader = ranking[0].provider if ranking else "unknown"
    deadline_days = int(case.signals.get("deadline_days", 45) or 45)
    console.print("[bold]Current mission[/bold]")
    console.print(f"Delivery window\n{deadline_days} days\n")
    console.print("Current mission statement")
    console.print(_mission_statement(case, leader, deadline_days))
    console.print("\nDominant risk")
    console.print(_dominant_risk(case, ranking))
    console.print("\nCurrent decision frame")
    console.print(_decision_frame(case, ranking))
    console.print(f"\nCurrent factual leader\n{leader}\n")



def show_paths(case_key: str) -> None:
    base = f"data/cases/{case_key}"
    console.print("[bold]Case files[/bold]")
    console.print(f"Case\n{base}/case.json\n")
    console.print("Baseline")
    console.print(f"{base}/baseline/providers.json")
    console.print(f"{base}/baseline/stakeholders.json")
    console.print(f"{base}/baseline/constraints.json\n")
    console.print("Proposals")
    console.print(f"{base}/artifacts/proposals/alpha_v1.pdf")
    console.print(f"{base}/artifacts/proposals/beta_v1.pdf")
    console.print(f"{base}/artifacts/proposals/coredesk_v1.pdf")
    console.print(f"{base}/artifacts/proposals/deltaflow_v1.pdf\n")





def show_baseline(case: CaseState) -> None:
    console.print("[bold]Negotiation baseline[/bold]")
    for offer in case.providers.values():
        console.print(f"\n[bold]{offer.name}[/bold]")
        console.print(f"- Price: €{offer.price}")
        console.print(f"- Term: {offer.term_months} months")
        console.print(f"- Payment: {offer.payment}")
    console.print()

def show_current_state(case: CaseState) -> None:
    console.print("[bold]Current factual state[/bold]")
    for offer in case.providers.values():
        console.print(f"\n[bold]{offer.name}[/bold]")
        console.print(f"- Price: €{offer.price}")
        console.print(f"- Term: {offer.term_months} months")
        console.print(f"- Payment: {offer.payment}")
    console.print("\n[bold]Open blockers[/bold]")
    for b in case.open_blockers:
        console.print(f"- {b}")
    console.print()



def show_recent_changes(case: CaseState) -> None:
    changes = case.signals.get("recent_changes") or []
    if not changes:
        return
    console.print("[bold]What changed[/bold]")
    for change in changes[-5:]:
        console.print(f"- {change}")
    console.print()



def show_active_strategy(case: CaseState) -> None:
    branch = case.signals.get("active_branch")
    if isinstance(branch, dict):
        console.print("[bold]Active strategy branch[/bold]")
        console.print(f"Label\n{branch.get('label', 'unknown')}\n")
        console.print(f"Type\n{branch.get('kind', 'unknown')}\n")
        if branch.get("target_provider"):
            console.print(f"Target provider\n{branch['target_provider']}\n")
        console.print(f"Projected leader\n{branch.get('projected_leader', 'unknown')}\n")
        console.print(f"Branch freshness\n{'stale' if branch.get('stale') else 'fresh'}\n")
        if branch.get("stale_reason"):
            console.print(f"Stale reason\n{branch['stale_reason']}\n")
        notes = branch.get("notes") or []
        if notes:
            console.print("Branch notes")
            for note in notes:
                console.print(f"- {note}")
        console.print("Factual state changed\nno\n")

    plan = case.signals.get("active_plan")
    if isinstance(plan, dict):
        console.print("[bold]Committed next move[/bold]")
        console.print(f"Action\n{plan.get('label', 'unknown')}\n")
        console.print(f"Owner\n{plan.get('owner', 'unknown')}\n")
        console.print(f"Plan type\n{plan.get('kind', 'unknown')}\n")
        console.print(f"Plan freshness\n{'stale' if plan.get('stale') else 'fresh'}\n")
        if plan.get("stale_reason"):
            console.print(f"Stale reason\n{plan['stale_reason']}\n")



def show_ranking(title: str, ranking: list[RankingRow]) -> None:
    console.print(f"[bold]{title}[/bold]")
    for row in ranking:
        t = Table.grid(padding=(0, 2))
        t.add_column()
        t.add_column()
        t.add_row("Close probability:", str(row.metrics.close_probability))
        t.add_row("Risk-adjusted value:", str(row.metrics.risk_adjusted_value))
        t.add_row("Blocker burden:", str(row.metrics.blocker_burden))
        t.add_row("Uncertainty:", str(row.metrics.uncertainty))
        console.print(Panel(t, title=f"{row.rank}. {row.provider}", border_style="green"))
        console.print("Provider content")
        console.print(f"- Price: €{row.offer.price}")
        console.print(f"- Term: {row.offer.term_months} months")
        console.print(f"- Payment: {row.offer.payment}")
        for s in row.offer.strengths[:3]:
            console.print(f"- {s}")
        for w in row.offer.weaknesses[:3]:
            console.print(f"- {w}")
        if row.metrics.metric_drivers:
            console.print("Metric drivers")
            for m in row.metrics.metric_drivers:
                console.print(f"- {m}")
        console.print()



def show_projection(title: str, projection: SimulationProjection) -> None:
    console.print(f"[bold]{title}[/bold]")
    console.print(f"Projected branch label\n{projection.label}\n")
    if projection.target_provider:
        console.print(f"Target provider\n{projection.target_provider}\n")
    console.print(f"Projected leader\n{projection.projected_leader}\n")
    for note in projection.notes:
        console.print(f"- {note}")
    if projection.notes:
        console.print()
    show_ranking("Projected ranking", projection.ranking)



def show_event(event: CaseEvent, deltas: list[tuple[str, object, object]], notes: list[str]) -> None:
    console.print("[bold]New event[/bold]")
    console.print(f"Source file\n{event.source_file}\n")
    console.print(f"Event\n{event.title}\n")
    console.print("[bold]Detected changes[/bold]")
    if not deltas:
        console.print("No structured field deltas were extracted")
    for field, before, after in deltas:
        console.print(f"{field}: {before} -> {after}")
    for note in notes:
        console.print(f"- {note}")
    console.print()



def show_decision(payload: ExplanationPayload) -> None:
    console.print("[bold]Agent decision[/bold]")
    console.print(f"Next action\n{payload.action}\n")
    console.print(f"Action score:                   {payload.action_score}")
    console.print(f"Expected close-readiness delta: +{payload.expected_close_delta:.2f}")
    console.print(f"Expected blocker reduction:     -{payload.expected_blocker_reduction:.2f}")
    console.print(f"Expected risk reduction:        -{payload.expected_risk_reduction:.2f}")
    console.print(f"Autonomy eligibility:           {'yes' if payload.autonomy_eligible else 'review required'}")
    console.print(f"Confidence:                     {payload.confidence}\n")
    console.print("[bold]Why this action wins[/bold]")
    for r in payload.reasons:
        console.print(f"- {r}")
    console.print()



def show_commit_ack(case: CaseState, payload: ExplanationPayload, already_committed: bool = False) -> None:
    console.print("[bold]Committed plan[/bold]")
    console.print(f"Action\n{payload.action}\n")
    console.print(f"Lifecycle\n{case.lifecycle}\n")
    if already_committed:
        console.print("Meaning")
        console.print("This move was already committed earlier. DSSE kept the case open because no new factual evidence or terminal outcome has been recorded yet.\n")
    elif case.lifecycle in {"completed", "cancelled", "failed", "archived"}:
        console.print("Meaning")
        console.print("This action moved the case into a terminal lifecycle. The interactive run can close because the case now has a final operational status.\n")
    else:
        console.print("Meaning")
        console.print("This commits the next move, not the final business outcome. The case stays open until confirming, contradictory, or terminal evidence is recorded.\n")
    if case.next_expected_action:
        console.print(f"Next expected evidence\n{case.next_expected_action}\n")


def show_next_menu(case: CaseState | None = None) -> None:
    console.print("[bold]Next[/bold]")
    if case and case.lifecycle == "ready":
        console.print("1. accept autonomous action (re-acknowledge committed plan)")
        console.print("2. inspect action math")
        console.print("3. simulate alternative")
        console.print("4. override committed plan")
        console.print("5. ingest confirming or contradictory event")
    else:
        console.print("1. accept autonomous action")
        console.print("2. inspect action math")
        console.print("3. simulate alternative")
        console.print("4. override")
        console.print("5. ingest sample event")
    console.print("6. exit\n")
