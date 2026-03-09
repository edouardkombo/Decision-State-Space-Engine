from __future__ import annotations

from dsse.models import ProviderMetrics, ProviderOffer, RankingRow


def _text(items: list[str]) -> str:
    return " ".join(item.lower() for item in items)


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def score_offer(offer: ProviderOffer, blockers: list[str], signals: dict | None = None) -> ProviderMetrics:
    signals = signals or {}
    strengths_text = _text(offer.strengths)
    weaknesses_text = _text(offer.weaknesses)
    provider_blockers = [b.lower() for b in blockers if offer.name.lower() in b.lower()]
    blocker_text = " ".join(provider_blockers)

    price_component = max(0.0, min(1.0, (160000 - offer.price) / 50000))
    term_penalty = 0.08 if offer.term_months > 24 else 0.0
    prepay_penalty = 0.12 if "upfront" in offer.payment.lower() else 0.0
    if _contains_any(strengths_text, ("finance exception granted",)):
        prepay_penalty = max(0.0, prepay_penalty - 0.10)
    quarterly_penalty = 0.03 if "quarterly" in offer.payment.lower() else 0.0

    execution_bonus = 0.05
    if _contains_any(strengths_text, ("implementation", "delivery confidence")):
        execution_bonus += 0.11
    if _contains_any(strengths_text, ("strong technical feature fit",)):
        execution_bonus += 0.04
    if _contains_any(strengths_text, ("cooperative legal posture",)):
        execution_bonus += 0.05
    if _contains_any(strengths_text, ("legal fallback approved", "finance exception granted")):
        execution_bonus += 0.05
    if _contains_any(strengths_text, ("free onboarding", "commercial flexibility")):
        execution_bonus += 0.03
    if _contains_any(strengths_text, ("delivery validation completed",)):
        execution_bonus += 0.05
    if _contains_any(strengths_text, ("finance workstream engaged",)):
        execution_bonus += 0.02
    execution_bonus = min(0.30, execution_bonus)

    security_penalty = 0.12 if _contains_any(weaknesses_text + " " + blocker_text, ("security",)) else 0.0
    legal_penalty = 0.10 if _contains_any(weaknesses_text + " " + blocker_text, ("legal", "liability")) else 0.0
    if _contains_any(strengths_text, ("legal fallback approved",)) and not _contains_any(blocker_text, ("legal", "liability")):
        legal_penalty = 0.0
    ambiguity_penalty = 0.10 if _contains_any(weaknesses_text + " " + blocker_text, ("unclear", "ambiguous", "clarity")) else 0.0
    delivery_penalty = 0.14 if _contains_any(weaknesses_text + " " + blocker_text, ("delivery promise may be unrealistic", "delivery confidence risk", "implementation capacity uncertain", "subcontractor")) else 0.0
    if _contains_any(strengths_text, ("delivery validation completed",)) and delivery_penalty:
        delivery_penalty = max(0.0, delivery_penalty - 0.09)
    contradiction_penalty = 0.14 if _contains_any(weaknesses_text + " " + blocker_text, ("contradictory",)) else 0.0

    blocker_factor = min(0.65, 0.08 * len(provider_blockers))

    deadline_days = int(signals.get("deadline_days", 45) or 45)
    deadline_bonus = 0.08 if deadline_days <= 30 and _contains_any(strengths_text, ("implementation", "delivery confidence", "cooperative legal posture")) else 0.0
    deadline_penalty = 0.08 if deadline_days <= 30 and delivery_penalty else 0.0

    projection_target = str(signals.get("projection_target", "")).lower().strip()
    projection_bonus = 0.04 if projection_target and offer.name.lower() == projection_target else 0.0

    close_probability = max(
        0.05,
        min(
            0.95,
            0.36
            + price_component * 0.22
            + execution_bonus
            + deadline_bonus
            + projection_bonus
            - term_penalty
            - prepay_penalty
            - quarterly_penalty
            - security_penalty
            - legal_penalty
            - ambiguity_penalty
            - delivery_penalty
            - contradiction_penalty
            - deadline_penalty
            - blocker_factor,
        ),
    )

    risk_adjusted_value = round(
        (close_probability * 100)
        - (security_penalty + legal_penalty + ambiguity_penalty + delivery_penalty + contradiction_penalty + prepay_penalty + quarterly_penalty) * 45,
        1,
    )
    blocker_burden = round(min(0.95, blocker_factor + security_penalty + legal_penalty + ambiguity_penalty + delivery_penalty + contradiction_penalty), 2)
    uncertainty = round(min(0.95, 0.08 + ambiguity_penalty + contradiction_penalty + (0.07 if delivery_penalty else 0.0)), 2)

    drivers: list[str] = []
    if execution_bonus >= 0.14:
        drivers.append("strong execution confidence")
    if prepay_penalty:
        drivers.append("finance resistance to upfront payment")
    if legal_penalty:
        drivers.append("legal blocker remains")
    if security_penalty:
        drivers.append("security blocker remains")
    if ambiguity_penalty:
        drivers.append("pricing or compliance ambiguity remains")
    if delivery_penalty:
        drivers.append("execution confidence needs validation")
    if contradiction_penalty:
        drivers.append("evidence conflict reduces trust")
    if deadline_bonus:
        drivers.append("deadline pressure favors safer execution")
    if projection_bonus:
        drivers.append("projected strategy focus favors this lane")
    if offer.price <= 130000:
        drivers.append("commercial position improved")

    return ProviderMetrics(
        close_probability=round(close_probability, 2),
        risk_adjusted_value=risk_adjusted_value,
        blocker_burden=blocker_burden,
        uncertainty=uncertainty,
        metric_drivers=drivers,
    )



def rank_offers(offers: dict[str, ProviderOffer], blockers: list[str], signals: dict | None = None) -> list[RankingRow]:
    rows = [RankingRow(provider=name, offer=offer, metrics=score_offer(offer, blockers, signals)) for name, offer in offers.items()]
    rows.sort(key=lambda r: (r.metrics.close_probability, r.metrics.risk_adjusted_value, -r.metrics.blocker_burden), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row.rank = idx
    return rows
