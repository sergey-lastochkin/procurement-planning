from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from procurement.planner import (
    ApprovalService,
    ItemState,
    Offer,
    Planner,
    PlanningPolicy,
    RecommendationStatus,
    candidate_qty,
    round_pack,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def state(**overrides):
    values = dict(
        sku="SKU-X",
        physical=Decimal("0"),
        reserved=Decimal("0"),
        demand=Decimal("20"),
        incoming=Decimal("0"),
        safety=Decimal("5"),
    )
    values.update(overrides)
    return ItemState(**values)


def offer(name="Supplier-A", **overrides):
    values = dict(
        supplier=name,
        price=Decimal("10"),
        currency="RUB",
        stock=Decimal("1000"),
        moq=Decimal("5"),
        pack=Decimal("5"),
        lead_days=2,
        reliability=Decimal("0.95"),
        observed_at=NOW,
        fresh_until=NOW + timedelta(days=3),
    )
    values.update(overrides)
    return Offer(**values)


def test_reserved_stock_reduces_available():
    item = state(physical=Decimal("30"), reserved=Decimal("20"), demand=Decimal("12"))
    assert item.available() == Decimal("10") and item.shortage() == Decimal("7")


def test_incoming_reduces_recommendation():
    item = state(demand=Decimal("30"), incoming=Decimal("20"), safety=Decimal("5"))
    assert Planner().plan(item, [offer()], "r", NOW).qty == Decimal("15")


def test_pack_rounding_ceil():
    assert round_pack(Decimal("11"), Decimal("6")) == Decimal("12")


def test_zero_pack_is_invalid():
    with pytest.raises(ValueError):
        round_pack(Decimal("1"), Decimal("0"))


def test_minimum_order_value_increases_quantity():
    supplier_offer = offer(price=Decimal("10"), minimum_order_value=Decimal("500"))
    assert candidate_qty(Decimal("12"), supplier_offer) == Decimal("50")


def test_foreign_currency_needs_review_without_rate():
    result = Planner().plan(state(), [offer(currency="USD")], "r", NOW)
    assert result.status == RecommendationStatus.NEEDS_REVIEW
    assert "currency_rate_missing" in result.evidence[0].constraints


def test_future_observation_is_not_fresh():
    result = Planner().plan(
        state(), [offer(observed_at=NOW + timedelta(days=1))], "r", NOW
    )
    assert result.supplier is None


def test_lead_time_policy_is_hard_constraint():
    result = Planner(policy=PlanningPolicy(max_lead_days=4)).plan(
        state(), [offer(lead_days=5)], "r", NOW
    )
    assert result.supplier is None


def test_preferred_credit_can_win_close_offer():
    preferred = offer("P", price=Decimal("10.10"), preferred=True)
    other = offer("N", price=Decimal("10.20"))
    assert Planner().plan(state(), [other, preferred], "r", NOW).supplier == "P"


def test_preferred_does_not_bypass_stock_constraint():
    preferred = offer("P", stock=Decimal("1"), preferred=True)
    other = offer("N")
    assert Planner().plan(state(), [preferred, other], "r", NOW).supplier == "N"


def test_invalid_locked_supplier_forbids_fallback():
    locked = offer("L", stock=Decimal("1"), locked=True)
    result = Planner().plan(state(), [locked, offer("N")], "r", NOW)
    assert result.supplier is None and any(
        "fallback" in warning for warning in result.warnings
    )


def test_deterministic_supplier_tie_break():
    result = Planner().plan(state(), [offer("B"), offer("A")], "r", NOW)
    assert result.supplier == "A"


def test_reliability_changes_explainable_score():
    reliable = offer("R", reliability=Decimal("0.99"))
    risky = offer("X", reliability=Decimal("0.50"))
    result = Planner().plan(state(), [risky, reliable], "r", NOW)
    assert result.supplier == "R"
    assert "reliability_penalty" in result.evidence[0].score_components


def test_invalid_negative_item_input():
    with pytest.raises(ValueError):
        Planner().plan(state(physical=Decimal("-1")), [offer()], "r", NOW)


def test_invalid_offer_price():
    with pytest.raises(ValueError):
        Planner().plan(state(), [offer(price=Decimal("0"))], "r", NOW)


def test_approval_is_idempotent():
    result = Planner().plan(state(), [offer()], "r", NOW)
    service = ApprovalService()
    service.add(result)
    assert service.approve(result.id) is service.approve(result.id)


def test_reject_created_draft_is_forbidden():
    result = Planner().plan(state(), [offer()], "r", NOW)
    service = ApprovalService()
    service.add(result)
    service.approve(result.id)
    service.create_draft(result.id)
    with pytest.raises(ValueError):
        service.reject(result.id)


def test_recommendation_evidence_has_all_inputs():
    result = Planner().plan(state(), [offer()], "r", NOW)
    assert set(result.inputs) == {
        "physical",
        "reserved",
        "available",
        "incoming",
        "demand",
        "projected",
        "safety_stock",
    }
