from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from hashlib import sha256

ZERO = Decimal("0")


class RecommendationStatus(StrEnum):
    CALCULATED = "calculated"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DRAFT_CREATED = "draft_created"


class PlanningError(RuntimeError):
    code = "PLANNING_ERROR"


class ConstraintError(PlanningError):
    code = "NO_FEASIBLE_OFFER"


@dataclass(frozen=True, slots=True)
class ItemState:
    sku: str
    physical: Decimal
    reserved: Decimal
    demand: Decimal
    incoming: Decimal
    safety: Decimal

    def available(self) -> Decimal:
        return self.physical - self.reserved

    def projected(self) -> Decimal:
        return self.available() + self.incoming - self.demand

    def shortage(self) -> Decimal:
        return max(ZERO, self.safety - self.projected())

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("sku is required")
        for name in ("physical", "reserved", "demand", "incoming", "safety"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class Offer:
    supplier: str
    price: Decimal
    currency: str
    stock: Decimal
    moq: Decimal
    pack: Decimal
    lead_days: int
    reliability: Decimal
    observed_at: datetime
    fresh_until: datetime
    preferred: bool = False
    locked: bool = False
    minimum_order_value: Decimal = ZERO

    def fresh(self, now: datetime) -> bool:
        return self.observed_at <= now <= self.fresh_until

    def validate(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.stock < 0 or self.moq < 0 or self.pack <= 0:
            raise ValueError("stock/moq/pack constraints are invalid")
        if not ZERO <= self.reliability <= Decimal("1"):
            raise ValueError("reliability must be in [0,1]")


@dataclass(frozen=True, slots=True)
class PlanningPolicy:
    max_lead_days: int = 30
    base_currency: str = "RUB"
    price_weight: Decimal = Decimal("1")
    lead_day_cost: Decimal = Decimal("0.25")
    unreliability_cost: Decimal = Decimal("20")
    preferred_credit: Decimal = Decimal("5")
    require_fresh_data: bool = True


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    supplier: str
    feasible: bool
    requested_qty: Decimal
    landed_value: Decimal
    total_score: Decimal
    score_components: dict[str, str]
    constraints: tuple[str, ...]
    observed_at: str


@dataclass(slots=True)
class Recommendation:
    id: str
    sku: str
    shortage: Decimal
    qty: Decimal
    supplier: str | None
    status: str
    reason: list[str]
    inputs: dict[str, str]
    candidates: list[dict[str, object]]
    warnings: list[str] = field(default_factory=list)
    evidence: tuple[CandidateEvidence, ...] = ()
    calculation_version: str = "planner.v2"
    approved_by: str | None = None

    def fingerprint(self) -> str:
        raw = json.dumps(
            {
                "id": self.id,
                "sku": self.sku,
                "qty": str(self.qty),
                "supplier": self.supplier,
                "inputs": self.inputs,
            },
            sort_keys=True,
        )
        return sha256(raw.encode()).hexdigest()


def round_pack(quantity: Decimal, pack: Decimal) -> Decimal:
    if pack <= 0:
        raise ValueError("pack must be positive")
    return (quantity / pack).to_integral_value(rounding=ROUND_CEILING) * pack


def candidate_qty(shortage: Decimal, offer: Offer) -> Decimal:
    minimum_value_qty = (
        offer.minimum_order_value / offer.price
        if offer.minimum_order_value > 0
        else ZERO
    )
    return round_pack(max(shortage, offer.moq, minimum_value_qty), offer.pack)


def score(
    offer: Offer, quantity: Decimal, policy: PlanningPolicy | None = None
) -> Decimal:
    policy = policy or PlanningPolicy()
    landed = offer.price * quantity
    lead_penalty = Decimal(offer.lead_days) * policy.lead_day_cost
    reliability_penalty = (Decimal("1") - offer.reliability) * policy.unreliability_cost
    preferred_credit = policy.preferred_credit if offer.preferred else ZERO
    return (
        landed * policy.price_weight
        + lead_penalty
        + reliability_penalty
        - preferred_credit
    )


class Planner:
    def __init__(
        self, max_lead: int = 30, policy: PlanningPolicy | None = None
    ) -> None:
        self.policy = policy or PlanningPolicy(max_lead_days=max_lead)

    def _evaluate(
        self, offer: Offer, shortage: Decimal, now: datetime
    ) -> CandidateEvidence:
        offer.validate()
        quantity = candidate_qty(shortage, offer)
        constraints: list[str] = []
        if self.policy.require_fresh_data and not offer.fresh(now):
            constraints.append("stale")
        if offer.stock < quantity:
            constraints.append("insufficient_stock")
        if offer.lead_days > self.policy.max_lead_days:
            constraints.append("lead_time_exceeded")
        if offer.currency.upper() != self.policy.base_currency.upper():
            constraints.append("currency_rate_missing")
        landed = offer.price * quantity
        components = {
            "landed_value": str(landed),
            "lead_penalty": str(Decimal(offer.lead_days) * self.policy.lead_day_cost),
            "reliability_penalty": str(
                (Decimal("1") - offer.reliability) * self.policy.unreliability_cost
            ),
            "preferred_credit": str(
                self.policy.preferred_credit if offer.preferred else ZERO
            ),
        }
        return CandidateEvidence(
            supplier=offer.supplier,
            feasible=not constraints,
            requested_qty=quantity,
            landed_value=landed,
            total_score=score(offer, quantity, self.policy),
            score_components=components,
            constraints=tuple(constraints),
            observed_at=offer.observed_at.isoformat(),
        )

    def plan(
        self,
        state: ItemState,
        offers: list[Offer],
        run_id: str,
        now: datetime | None = None,
    ) -> Recommendation:
        state.validate()
        now = now or datetime.now(timezone.utc)
        shortage = state.shortage()
        recommendation_id = sha256(
            f"{run_id}:{state.sku}:planner.v2".encode()
        ).hexdigest()[:16]
        inputs = {
            "physical": str(state.physical),
            "reserved": str(state.reserved),
            "available": str(state.available()),
            "incoming": str(state.incoming),
            "demand": str(state.demand),
            "projected": str(state.projected()),
            "safety_stock": str(state.safety),
        }
        if shortage <= 0:
            return Recommendation(
                recommendation_id,
                state.sku,
                shortage,
                ZERO,
                None,
                RecommendationStatus.CALCULATED,
                ["projected balance covers safety stock"],
                inputs,
                [],
            )

        evidence = tuple(self._evaluate(offer, shortage, now) for offer in offers)
        candidates = [
            {
                "supplier": item.supplier,
                "qty": str(item.requested_qty),
                "score": str(item.total_score),
                "price_value": str(item.landed_value),
                "constraints": list(item.constraints),
                "score_components": item.score_components,
            }
            for item in evidence
        ]
        offer_by_supplier = {offer.supplier: offer for offer in offers}
        locked = [item for item in evidence if offer_by_supplier[item.supplier].locked]
        pool = locked if locked else list(evidence)
        feasible = [item for item in pool if item.feasible]
        warnings = [
            f"{item.supplier}: {','.join(item.constraints)}"
            for item in evidence
            if item.constraints
        ]
        if locked and not feasible:
            warnings.append(
                "locked supplier is not feasible; automatic fallback is forbidden"
            )
        if not feasible:
            return Recommendation(
                recommendation_id,
                state.sku,
                shortage,
                ZERO,
                None,
                RecommendationStatus.NEEDS_REVIEW,
                ["no supplier satisfies hard constraints"],
                inputs,
                candidates,
                warnings,
                evidence,
            )
        selected = min(feasible, key=lambda item: (item.total_score, item.supplier))
        selected_offer = offer_by_supplier[selected.supplier]
        reason = [
            f"shortage {shortage}",
            f"selected {selected.supplier}",
            f"MOQ {selected_offer.moq}",
            f"pack {selected_offer.pack}",
            f"lead {selected_offer.lead_days}d",
            f"score {selected.total_score}",
        ]
        if locked:
            reason.append("locked supplier constraint applied")
        elif selected_offer.preferred:
            reason.append("preferred supplier score credit applied")
        return Recommendation(
            recommendation_id,
            state.sku,
            shortage,
            selected.requested_qty,
            selected.supplier,
            RecommendationStatus.CALCULATED,
            reason,
            inputs,
            candidates,
            warnings,
            evidence,
        )


class ApprovalService:
    def __init__(self) -> None:
        self.recs: dict[str, Recommendation] = {}
        self.created: dict[str, tuple[str, str]] = {}

    def add(self, recommendation: Recommendation) -> Recommendation:
        existing = self.recs.get(recommendation.id)
        if existing and existing.fingerprint() != recommendation.fingerprint():
            raise ValueError("recommendation id collision")
        self.recs.setdefault(recommendation.id, recommendation)
        return self.recs[recommendation.id]

    def approve(
        self, recommendation_id: str, actor: str = "synthetic-reviewer"
    ) -> Recommendation:
        recommendation = self.recs[recommendation_id]
        if recommendation.status == RecommendationStatus.APPROVED:
            return recommendation
        if not recommendation.supplier or recommendation.qty <= 0:
            raise ValueError("nothing to approve")
        if recommendation.status not in {
            RecommendationStatus.CALCULATED,
            RecommendationStatus.NEEDS_REVIEW,
        }:
            raise ValueError(f"cannot approve {recommendation.status}")
        recommendation.status = RecommendationStatus.APPROVED
        recommendation.approved_by = actor
        return recommendation

    def reject(self, recommendation_id: str) -> None:
        recommendation = self.recs[recommendation_id]
        if recommendation.status == RecommendationStatus.DRAFT_CREATED:
            raise ValueError("created draft cannot be rejected here")
        recommendation.status = RecommendationStatus.REJECTED

    def create_draft(self, recommendation_id: str) -> str:
        recommendation = self.recs[recommendation_id]
        if recommendation.status == RecommendationStatus.DRAFT_CREATED:
            return self.created[recommendation_id][0]
        if recommendation.status != RecommendationStatus.APPROVED:
            raise PermissionError("approval required")
        reference = "draft-po-" + recommendation_id
        self.created[recommendation_id] = (reference, recommendation.fingerprint())
        recommendation.status = RecommendationStatus.DRAFT_CREATED
        return reference


def synthetic(
    n: int = 500, suppliers: int = 5, seed: int = 23
) -> list[tuple[ItemState, list[Offer]]]:
    random_generator = random.Random(seed)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data: list[tuple[ItemState, list[Offer]]] = []
    for index in range(n):
        state = ItemState(
            f"SKU-{index:04d}",
            Decimal(index % 40),
            Decimal(index % 7),
            Decimal(10 + index % 30),
            Decimal(index % 9),
            Decimal(5),
        )
        supplier_offers = [
            Offer(
                f"Supplier-{supplier_index}",
                Decimal(10 + supplier_index)
                + Decimal(random_generator.randrange(0, 20)) / 100,
                "RUB",
                Decimal(1000),
                Decimal(5),
                Decimal(5),
                supplier_index + 1,
                Decimal("0.95") - Decimal(supplier_index) / 100,
                now,
                now + timedelta(days=7),
                preferred=supplier_index == 0 and index % 3 == 0,
            )
            for supplier_index in range(suppliers)
        ]
        data.append((state, supplier_offers))
    return data
