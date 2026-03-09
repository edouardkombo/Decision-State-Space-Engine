from dsse.models import ProviderOffer
from dsse.scoring import rank_offers, score_offer


def test_score_offer_prefers_lower_price_when_other_factors_are_equal():
    a = ProviderOffer(name="A", price=120000, term_months=12, payment="staged")
    b = ProviderOffer(name="B", price=150000, term_months=12, payment="staged")
    assert score_offer(a, []).close_probability > score_offer(b, []).close_probability


def test_rank_offers_assigns_rank_order():
    offers = {
        "A": ProviderOffer(name="A", price=120000, term_months=12, payment="staged"),
        "B": ProviderOffer(name="B", price=150000, term_months=36, payment="annual upfront"),
    }
    rows = rank_offers(offers, [])
    assert rows[0].rank == 1
    assert rows[1].rank == 2


def test_deadline_pressure_rewards_execution_confidence():
    safe = ProviderOffer(name="Safe", price=130000, term_months=24, payment="net 30", strengths=["highest delivery confidence"])
    risky = ProviderOffer(name="Risky", price=125000, term_months=24, payment="net 30", weaknesses=["delivery promise may be unrealistic"])
    safe_score = score_offer(safe, [], {"deadline_days": 30}).close_probability
    risky_score = score_offer(risky, [], {"deadline_days": 30}).close_probability
    assert safe_score > risky_score
