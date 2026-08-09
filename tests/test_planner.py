from datetime import datetime, timedelta, timezone
from decimal import Decimal

from procurement.planner import *

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def offer(name="A", **kw):
    d = dict(
        price=Decimal("10"),
        currency="RUB",
        stock=Decimal("1000"),
        moq=Decimal("10"),
        pack=Decimal("5"),
        lead_days=2,
        reliability=Decimal("0.9"),
        observed_at=NOW,
        fresh_until=NOW + timedelta(days=2),
    )
    d.update(kw)
    return Offer(name, **d)


def test_no_order():
    assert (
        Planner().plan(ItemState("x", 100, 0, 10, 0, 5), [offer()], "r", NOW).qty == 0
    )


def test_shortage_and_pack_moq():
    r = Planner().plan(
        ItemState("x", 0, 0, 12, 0, 3),
        [offer(moq=Decimal("20"), pack=Decimal("10"))],
        "r",
        NOW,
    )
    assert r.qty == 20


def test_incoming_covers():
    assert (
        Planner().plan(ItemState("x", 0, 0, 10, 20, 5), [offer()], "r", NOW).supplier
        is None
    )


def test_cheapest_no_stock_selects_other():
    r = Planner().plan(
        ItemState("x", 0, 0, 20, 0, 0),
        [offer("cheap", stock=Decimal("1")), offer("ok", price=Decimal("12"))],
        "r",
        NOW,
    )
    assert r.supplier == "ok"


def test_stale_requires_review():
    r = Planner().plan(
        ItemState("x", 0, 0, 20, 0, 0),
        [offer(fresh_until=NOW - timedelta(seconds=1))],
        "r",
        NOW,
    )
    assert r.status == "needs_review"


def test_locked_supplier():
    r = Planner().plan(
        ItemState("x", 0, 0, 20, 0, 0),
        [offer("cheap"), offer("locked", price=Decimal("50"), locked=True)],
        "r",
        NOW,
    )
    assert r.supplier == "locked"


def test_duplicate_approval_and_draft():
    r = Planner().plan(ItemState("x", 0, 0, 20, 0, 0), [offer()], "r", NOW)
    s = ApprovalService()
    s.add(r)
    s.approve(r.id)
    a = s.create_draft(r.id)
    b = s.create_draft(r.id)
    assert a == b


def test_approval_required():
    r = Planner().plan(ItemState("x", 0, 0, 20, 0, 0), [offer()], "r", NOW)
    s = ApprovalService()
    s.add(r)
    try:
        s.create_draft(r.id)
        assert False
    except PermissionError:
        pass


def test_same_run_deterministic_id():
    p = Planner()
    st = ItemState("x", 0, 0, 20, 0, 0)
    assert p.plan(st, [offer()], "run", NOW).id == p.plan(st, [offer()], "run", NOW).id


def test_synthetic_500():
    assert len(synthetic()) == 500
