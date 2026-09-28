"""Пример: дефицит по SKU и выбор поставщика с учётом остатка, MOQ и упаковки."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from procurement.planner import ItemState, Offer, Planner

now = datetime(2026, 1, 1, tzinfo=timezone.utc)
def offer(name, price, stock, moq, pack, lead):
    return Offer(name, price=D(price), currency="RUB", stock=D(stock), moq=D(moq), pack=D(pack),
                 lead_days=lead, reliability=D("0.9"), observed_at=now, fresh_until=now + timedelta(days=2))

item = ItemState("SKU-1", physical=D(40), reserved=D(25), demand=D(60), incoming=D(10), safety=D(20))
offers = [offer("Дешёвый", "9.50", "30", "10", "10", 3),      # мало остатка
          offer("Надёжный", "10.20", "500", "50", "25", 2)]
r = Planner().plan(item, offers, "demo", now)
print("дефицит:", item.shortage())
print("поставщик:", r.supplier, "| количество:", r.qty, "| статус:", r.status)
print("причина:", r.reason)
for e in r.evidence:
    print(" ", e.supplier, "допустим" if e.feasible else "отклонён", list(e.constraints))
