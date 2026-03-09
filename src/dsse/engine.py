from __future__ import annotations

from copy import deepcopy

import networkx as nx

from dsse.models import CaseEvent, CaseState, ExplanationPayload, RankingRow, SimulationProjection
from dsse.scoring import rank_offers


SIMULATION_META: dict[str, tuple[str, str | None]] = {
    "push_finance_now": ("push Finance now", "AlphaSoft"),
    "pressure_betastack_now": ("pressure BetaStack now", "BetaStack"),
    "validate_coredesk_delivery_now": ("validate CoreDesk delivery now", "CoreDesk"),
    "wait_supplier_movement": ("wait for more supplier movement", None),
}


class DSSEEngine:
    def __init__(self, case: CaseState):
        self.case = case
        self.graph = nx.DiGraph()
        self._build_graph()

    def _provider_key(self, provider_name: str) -> str:
        return provider_name.lower().replace(" ", "")

    def _record_change(self, message: str) -> None:
        changes = self.case.signals.setdefault("recent_changes", [])
        if not isinstance(changes, list):
            changes = []
            self.case.signals["recent_changes"] = changes
        if not changes or changes[-1] != message:
            changes.append(message)
        if len(changes) > 8:
            del changes[:-8]

    def _mark_active_branch_stale(self, reason: str) -> None:
        branch = self.case.signals.get("active_branch")
        if isinstance(branch, dict) and not branch.get("stale"):
            branch["stale"] = True
            branch["stale_reason"] = reason
            self._record_change(f"Strategy branch went stale: {reason}")

    def _mark_active_plan_stale(self, reason: str) -> None:
        plan = self.case.signals.get("active_plan")
        if isinstance(plan, dict) and not plan.get("stale"):
            plan["stale"] = True
            plan["stale_reason"] = reason
            self._record_change(f"Committed plan went stale: {reason}")

    def _clear_projection_bias(self) -> None:
        self.case.signals.pop("projection_target", None)

    def _provider_from_action(self, action: str) -> str | None:
        action_lower = action.lower()
        for provider_name in self.case.providers:
            if provider_name.lower() in action_lower:
                return provider_name
        return None

    def _build_graph(self) -> None:
        self.graph.clear()
        self.graph.add_node(self.case.case_key, kind="case")
        for provider in self.case.providers.values():
            self.graph.add_node(provider.name, kind="actor")
            self.graph.add_edge(self.case.case_key, provider.name, relation="contains")
        for blocker in self.case.open_blockers:
            blocker_id = f"blocker:{blocker}"
            self.graph.add_node(blocker_id, kind="constraint")
            self.graph.add_edge(self.case.case_key, blocker_id, relation="has_constraint")
            for provider in self.case.providers.values():
                provider_key = self._provider_key(provider.name)
                if provider.name.lower().split()[0] in blocker.lower() or provider_key in blocker.lower():
                    self.graph.add_edge(blocker_id, provider.name, relation="blocks")

    def current_ranking(self) -> list[RankingRow]:
        signals = dict(self.case.signals)
        signals.pop("projection_target", None)
        return rank_offers(self.case.providers, self.case.open_blockers, signals)

    def _append_unique(self, items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    def _remove_blocker(self, blocker_text: str) -> None:
        target = blocker_text.lower().strip()
        self.case.open_blockers = [b for b in self.case.open_blockers if b.lower().strip() != target]

    def _apply_global_event_effects(self, event: CaseEvent, notes: list[str]) -> None:
        if event.key == "010_requester_deadline_change":
            self.case.signals["deadline_days"] = 30
            notes.append("Global state updated: implementation window now treated as 30 days")
            self._record_change("Deadline compressed from 45 days to 30 days")
        if event.key == "011_finance_exception_reply":
            self.case.signals["finance_locked"] = True
            notes.append("Finance lane is now materially harder to reopen")
            self._record_change("Finance denied the exception request for AlphaSoft")
        if event.key == "015_final_finance_exception":
            self.case.signals["finance_locked"] = False
            notes.append("Finance lane reopened for the active leader")
            self._record_change("Finance reopened the AlphaSoft lane with a restricted exception")

    def apply_event(self, event: CaseEvent) -> tuple[list[tuple[str, object, object]], list[str]]:
        detected: list[tuple[str, object, object]] = []
        notes = list(event.notes)

        if event.provider and event.provider in self.case.providers:
            offer = self.case.providers[event.provider]
            for delta in event.deltas:
                detected.append((delta.field, delta.before, delta.after))
                if delta.field == "price":
                    offer.price = int(delta.after)
                    self._record_change(f"{event.provider} price changed to €{int(delta.after)}")
                elif delta.field == "term_months":
                    offer.term_months = int(delta.after)
                    self._record_change(f"{event.provider} term changed to {int(delta.after)} months")
                elif delta.field == "payment":
                    offer.payment = str(delta.after)
                    self._record_change(f"{event.provider} payment changed to {str(delta.after)}")
                elif delta.field == "add_strength":
                    self._append_unique(offer.strengths, str(delta.after))
                    self._record_change(f"{event.provider} gained evidence: {str(delta.after)}")
                elif delta.field == "add_weakness":
                    self._append_unique(offer.weaknesses, str(delta.after))
                    self._record_change(f"{event.provider} new concern: {str(delta.after)}")
                elif delta.field == "remove_blocker":
                    self._remove_blocker(str(delta.after or delta.before))
                    self._record_change(f"Blocker removed: {str(delta.after or delta.before)}")
                elif delta.field == "add_blocker":
                    self._append_unique(self.case.open_blockers, str(delta.after))
                    self._record_change(f"New blocker: {str(delta.after)}")
        else:
            for delta in event.deltas:
                detected.append((delta.field, delta.before, delta.after))
                if delta.field == "remove_blocker":
                    self._remove_blocker(str(delta.after or delta.before))
                    self._record_change(f"Blocker removed: {str(delta.after or delta.before)}")
                elif delta.field == "add_blocker":
                    self._append_unique(self.case.open_blockers, str(delta.after))
                    self._record_change(f"New blocker: {str(delta.after)}")

        self._apply_global_event_effects(event, notes)
        self._clear_projection_bias()
        stale_reason = f"new factual event arrived: {event.title}"
        self._mark_active_branch_stale(stale_reason)
        self._mark_active_plan_stale(stale_reason)
        self.case.history.append(event.key)
        self.case.status_reason = event.title
        self.case.current_owner = event.provider or "system"
        self.case.next_expected_action = self.recommend_action().action
        self._recompute_lifecycle()
        self._build_graph()
        return detected, notes

    def _recompute_lifecycle(self) -> None:
        ranking = self.current_ranking()
        leader = ranking[0]
        deadline_days = int(self.case.signals.get("deadline_days", 45) or 45)
        finance_locked = bool(self.case.signals.get("finance_locked", False))

        if leader.metrics.close_probability >= 0.65 and leader.metrics.blocker_burden <= 0.1:
            self.case.lifecycle = "ready"
        elif (
            leader.metrics.close_probability <= 0.18
            or all(row.metrics.blocker_burden >= 0.3 for row in ranking[:2])
            or (deadline_days <= 30 and finance_locked and leader.metrics.close_probability < 0.35)
        ):
            self.case.lifecycle = "blocked"
        elif self.case.history:
            self.case.lifecycle = "review"
        else:
            self.case.lifecycle = "active"

    def recommend_action(self) -> ExplanationPayload:
        ranking = self.current_ranking()
        leader = ranking[0]
        reasons: list[str] = []
        plan = self.case.signals.get("active_plan")
        if isinstance(plan, dict) and not plan.get("stale") and plan.get("label"):
            reasons.extend([
                "a committed move already exists and should not be re-accepted as if it were new evidence",
                "the next useful step is to gather confirming or disconfirming facts",
                "use a real event or override to move the case forward",
            ])
            return ExplanationPayload(str(plan["label"]), 0.66, 0.00, 0.00, 0.00, False, 0.73, reasons)
        leader_key = leader.provider.lower().split()[0]
        if any("legal" in b.lower() and leader_key in b.lower() for b in self.case.open_blockers):
            action = f"Align Legal on {leader.provider} fallback clause"
            reasons.extend([
                "largest remaining weighted blocker",
                "unlock breadth: 2 viable close paths",
                "no external concession required",
                "higher expected gain than a new price push",
            ])
            return ExplanationPayload(action, 0.86, 0.12, 0.18, 0.05, True, 0.80, reasons)
        if any("finance" in b.lower() and leader_key in b.lower() for b in self.case.open_blockers):
            action = f"Align Finance on {leader.provider} payment structure"
            reasons.extend([
                "finance is the largest remaining blocker",
                "improves close readiness without changing provider ranking",
                "required before any autonomous close",
            ])
            return ExplanationPayload(action, 0.82, 0.10, 0.14, 0.04, True, 0.77, reasons)
        if leader.metrics.close_probability < 0.3:
            action = "Pause close and collect missing evidence"
            reasons.extend([
                "no route is currently safe enough to close",
                "blocker burden remains too high",
                "new evidence is worth more than pressure tactics",
            ])
            return ExplanationPayload(action, 0.73, 0.06, 0.08, 0.07, False, 0.71, reasons)
        action = f"Prepare close on {leader.provider}"
        reasons.extend([
            "highest current close probability",
            "lowest blocker burden among viable paths",
            "strongest expected trajectory score",
        ])
        return ExplanationPayload(action, 0.91, 0.16, 0.10, 0.03, False, 0.84, reasons)

    def accept_recommendation(self) -> ExplanationPayload:
        payload = self.recommend_action()
        existing_plan = self.case.signals.get("active_plan")
        if isinstance(existing_plan, dict) and not existing_plan.get("stale") and existing_plan.get("label") == payload.action:
            return payload

        action_provider = self._provider_from_action(payload.action)
        branch = self.case.signals.get("active_branch")
        if isinstance(branch, dict) and not branch.get("stale"):
            branch_target = branch.get("target_provider")
            if branch_target and action_provider and branch_target != action_provider:
                self._mark_active_branch_stale(
                    f"committed action moved to {action_provider} instead of branch target {branch_target}"
                )

        self.case.status_reason = payload.action
        self.case.current_owner = "autonomous agent"
        self.case.next_expected_action = f"wait for evidence confirming: {payload.action}"
        self.case.signals["active_plan"] = {
            "label": payload.action,
            "owner": "autonomous agent",
            "kind": "committed_action",
            "target_provider": action_provider,
            "stale": False,
        }
        self._record_change(f"Committed next action: {payload.action}")
        action_lower = payload.action.lower()
        if action_lower.startswith("prepare close"):
            self.case.lifecycle = "ready"
        elif "align legal" in action_lower or "align finance" in action_lower:
            self.case.lifecycle = "review"
        else:
            self.case.lifecycle = "review"
        return payload

    def set_active_branch(self, projection: SimulationProjection) -> None:
        self.case.signals["active_branch"] = {
            "key": projection.key,
            "label": projection.label,
            "target_provider": projection.target_provider,
            "projected_leader": projection.projected_leader,
            "kind": "hypothetical_branch",
            "stale": False,
            "notes": list(projection.notes),
            "relation_to_facts": "aligned" if projection.projected_leader == projection.target_provider else "divergent",
        }
        self.case.status_reason = f"active strategy branch selected: {projection.label}"
        self.case.current_owner = "user"
        stale_plan = self.case.signals.get("active_plan")
        if isinstance(stale_plan, dict) and not stale_plan.get("stale"):
            self._mark_active_plan_stale(f"new hypothetical branch chosen: {projection.label}")
        if projection.target_provider:
            self.case.next_expected_action = f"gather evidence for {projection.target_provider}"
        else:
            self.case.next_expected_action = "monitor supplier movement before committing"
        self._record_change(f"Active strategy branch set: {projection.label}")
        if self.case.lifecycle == "ready":
            self.case.lifecycle = "review"

    def set_manual_override(self, action: str) -> None:
        self.case.status_reason = f"override: {action}"
        self.case.current_owner = "user"
        self.case.next_expected_action = action
        self.case.lifecycle = "review"
        self.case.signals["active_plan"] = {
            "label": action,
            "owner": "user",
            "kind": "manual_override",
        }
        self._record_change(f"Manual override set: {action}")

    def simulate_alternative(self, simulation_key: str) -> SimulationProjection:
        if simulation_key not in SIMULATION_META:
            raise ValueError(f"Unknown simulation '{simulation_key}'")

        label, target_provider = SIMULATION_META[simulation_key]
        snapshot = deepcopy(self.case)
        snapshot.signals["projection_target"] = (target_provider or "")
        notes: list[str] = []

        if simulation_key == "push_finance_now":
            snapshot.open_blockers = [
                b for b in snapshot.open_blockers if "alphasoft finance blocker on annual prepay" not in b.lower()
            ]
            self._append_unique(snapshot.providers["AlphaSoft"].strengths, "finance workstream engaged")
            notes.append("Projected effect: AlphaSoft prepay friction reduced for a finance-focused push")
        elif simulation_key == "pressure_betastack_now":
            snapshot.providers["BetaStack"].price = max(112000, snapshot.providers["BetaStack"].price - 6000)
            self._append_unique(snapshot.providers["BetaStack"].strengths, "commercial concession extracted under pressure")
            self._append_unique(snapshot.providers["BetaStack"].weaknesses, "pressure increases execution ambiguity")
            notes.append("Projected effect: BetaStack improves on price but trust remains fragile")
        elif simulation_key == "validate_coredesk_delivery_now":
            snapshot.open_blockers = [b for b in snapshot.open_blockers if "coredesk delivery confidence risk" not in b.lower()]
            self._append_unique(snapshot.providers["CoreDesk"].strengths, "delivery validation completed")
            notes.append("Projected effect: CoreDesk execution risk narrows after validation")
        elif simulation_key == "wait_supplier_movement":
            for offer in snapshot.providers.values():
                self._append_unique(offer.weaknesses, "delay increases uncertainty")
            notes.append("Projected effect: waiting increases ambiguity across all lanes")

        ranking = rank_offers(snapshot.providers, snapshot.open_blockers, snapshot.signals)
        return SimulationProjection(
            key=simulation_key,
            label=label,
            target_provider=target_provider,
            projected_leader=ranking[0].provider,
            ranking=ranking,
            notes=notes,
        )
