from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
from typing import Any

from .time_utils import parse_aware


class CommercialClassification(StrEnum):
    CONFIRMED = "CONFIRMED"
    OBSERVED = "OBSERVED"
    CALCULATED = "CALCULATED"
    ASSUMPTION = "ASSUMPTION"
    SIMULATION = "SIMULATION"
    UNKNOWN = "UNKNOWN"


class OwnershipKind(StrEnum):
    RIBEIRA_OWNED = "RIBEIRA_OWNED"
    CUSTOMER_OWNED = "CUSTOMER_OWNED"
    THIRD_PARTY = "THIRD_PARTY"
    LEASED = "LEASED"
    PASS_THROUGH = "PASS_THROUGH"  # nosec B105 - domain classification, not a secret
    UNKNOWN = "UNKNOWN"


class CapexClassification(StrEnum):
    RIBEIRA_CAPEX = "RIBEIRA_CAPEX"
    CUSTOMER_CAPEX = "CUSTOMER_CAPEX"
    THIRD_PARTY_CAPEX = "THIRD_PARTY_CAPEX"
    PASS_THROUGH = "PASS_THROUGH"  # nosec B105 - domain classification, not a secret
    UNKNOWN = "UNKNOWN"


class RevenueType(StrEnum):
    INSTALLATION_REVENUE = "INSTALLATION_REVENUE"
    RECURRING_REVENUE = "RECURRING_REVENUE"
    ONE_TIME_SERVICE = "ONE_TIME_SERVICE"
    CONSULTING = "CONSULTING"
    PASS_THROUGH = "PASS_THROUGH"  # nosec B105 - domain classification, not a secret
    OTHER = "OTHER"


class RevenueTreatment(StrEnum):
    RIBEIRA_RECURRING = "RIBEIRA_RECURRING"
    RIBEIRA_ONE_TIME = "RIBEIRA_ONE_TIME"
    CUSTOMER_DIRECT_EXTERNAL = "CUSTOMER_DIRECT_EXTERNAL"
    PASS_THROUGH = "PASS_THROUGH"  # nosec B105 - domain classification, not a secret
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class ProductStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PILOT = "PILOT"
    DISCONTINUED = "DISCONTINUED"


class OpportunityClassification(StrEnum):
    POTENTIAL_OPPORTUNITY = "POTENTIAL_OPPORTUNITY"
    CONFIRMED_NEED = "CONFIRMED_NEED"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    QUALIFIED_OPPORTUNITY = "QUALIFIED_OPPORTUNITY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpportunityStatus(StrEnum):
    OPEN = "OPEN"
    QUALIFIED = "QUALIFIED"
    CLOSED = "CLOSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CapacityStatus(StrEnum):
    WITHIN_CAPACITY = "WITHIN_CAPACITY"
    AT_CAPACITY = "AT_CAPACITY"
    CAPACITY_GATE_REQUIRED = "CAPACITY_GATE_REQUIRED"
    UNKNOWN = "UNKNOWN"


class PricingStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_PRICING = "INCOMPLETE_PRICING"
    INVALID_POLICY = "INVALID_POLICY"


class ConditionState(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


def decimal_value(
    value: Decimal | int | float | str, *, allow_negative: bool = False
) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("financial value must be a valid decimal") from exc
    if not result.is_finite() or (not allow_negative and result < 0):
        raise ValueError("financial value must be finite and non-negative")
    return result


def optional_decimal(
    value: Decimal | int | float | str | None, *, allow_negative: bool = False
) -> Decimal | None:
    return (
        None if value is None else decimal_value(value, allow_negative=allow_negative)
    )


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iso_timestamp(value: str) -> str:
    parse_aware(value)
    return value


@dataclass(frozen=True)
class Customer:
    id: str
    tenant_id: str
    customer_type: str
    display_name: str
    legal_name: str | None
    status: str
    classification: CommercialClassification = CommercialClassification.CONFIRMED
    external_reference: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class CustomerContract:
    id: str
    tenant_id: str
    customer_id: str
    property_id: str | None
    contract_type: str
    counterparty_name: str | None
    external_provider_name: str | None
    revenue_treatment: RevenueTreatment
    status: str
    start_at: str
    end_at: str | None
    classification: CommercialClassification
    created_at: str | None = None

    def __post_init__(self) -> None:
        iso_timestamp(self.start_at)
        if self.end_at is not None:
            iso_timestamp(self.end_at)
        if self.contract_type == "EXTERNAL_LINK" and self.revenue_treatment not in {
            RevenueTreatment.CUSTOMER_DIRECT_EXTERNAL,
            RevenueTreatment.EXCLUDED,
        }:
            raise ValueError("external link contract cannot become Ribeira revenue")


@dataclass(frozen=True)
class ContractVersion:
    id: str
    tenant_id: str
    contract_id: str
    version: int
    status: str
    valid_from: str
    valid_until: str | None
    total_price: Decimal | None
    currency: str
    recurring: bool
    configuration: dict[str, Any]
    created_by: str
    approved_by: str | None
    classification: CommercialClassification

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("contract version must be positive")
        iso_timestamp(self.valid_from)
        if self.valid_until is not None:
            iso_timestamp(self.valid_until)
        if self.total_price is not None:
            decimal_value(self.total_price)


@dataclass(frozen=True)
class Product:
    id: str
    tenant_id: str
    name: str
    category: str
    status: ProductStatus
    sku: str | None
    description: str | None
    classification: CommercialClassification


@dataclass(frozen=True)
class ServiceOffering:
    id: str
    tenant_id: str
    name: str
    category: str
    status: ProductStatus
    recurring: bool
    revenue_type: RevenueType
    product_id: str | None
    classification: CommercialClassification


@dataclass(frozen=True)
class ServicePlan:
    id: str
    tenant_id: str
    service_id: str
    name: str
    billing_period: str
    monthly_price: Decimal | None
    currency: str
    status: str
    revenue_treatment: RevenueTreatment
    classification: CommercialClassification

    def __post_init__(self) -> None:
        if self.monthly_price is not None:
            decimal_value(self.monthly_price)


@dataclass(frozen=True)
class Subscription:
    id: str
    tenant_id: str
    contract_id: str
    contract_version_id: str
    service_plan_id: str
    status: str
    start_at: str
    end_at: str | None
    monthly_price: Decimal | None
    currency: str
    recurring: bool
    mrr_eligible: bool
    revenue_treatment: RevenueTreatment
    classification: CommercialClassification

    def __post_init__(self) -> None:
        iso_timestamp(self.start_at)
        if self.end_at is not None:
            iso_timestamp(self.end_at)
        if self.monthly_price is not None:
            decimal_value(self.monthly_price)
        if self.revenue_treatment == RevenueTreatment.CUSTOMER_DIRECT_EXTERNAL:
            raise ValueError("customer-direct external subscription is not Ribeira MRR")


@dataclass(frozen=True)
class Site:
    id: str
    tenant_id: str
    property_id: str
    name: str
    site_type: str
    geometry_geojson: dict[str, Any] | None
    geometry_crs: str | None
    classification: CommercialClassification


@dataclass(frozen=True)
class InstallationProject:
    id: str
    tenant_id: str
    customer_id: str
    property_id: str | None
    name: str
    status: str
    technical_provider_type: str
    customer_total_project_cost: Decimal | None
    currency: str
    revenue_treatment: RevenueTreatment
    classification: CommercialClassification

    def __post_init__(self) -> None:
        if self.customer_total_project_cost is not None:
            decimal_value(self.customer_total_project_cost)
        if (
            self.technical_provider_type == "EXTERNAL_CONSULTANT"
            and self.revenue_treatment
            not in {
                RevenueTreatment.CUSTOMER_DIRECT_EXTERNAL,
                RevenueTreatment.EXCLUDED,
            }
        ):
            raise ValueError(
                "external consultant project cannot become Ribeira revenue"
            )


@dataclass(frozen=True)
class CapexItem:
    id: str
    tenant_id: str
    project_id: str | None
    asset_id: str | None
    description: str
    amount: Decimal | None
    currency: str
    capex_classification: CapexClassification
    ownership_kind: OwnershipKind
    purchased_by: str | None
    source: str | None
    classification: CommercialClassification

    def __post_init__(self) -> None:
        if self.amount is not None:
            decimal_value(self.amount)


@dataclass(frozen=True)
class PassThroughItem:
    id: str
    tenant_id: str
    project_id: str | None
    customer_id: str | None
    description: str
    amount: Decimal | None
    currency: str
    supplier: str | None
    document_reference: str | None
    paid_at: str | None
    classification: CommercialClassification

    def __post_init__(self) -> None:
        if self.amount is not None:
            decimal_value(self.amount)
        if self.paid_at is not None:
            iso_timestamp(self.paid_at)


@dataclass(frozen=True)
class Asset:
    id: str
    tenant_id: str
    asset_type: str
    name: str
    serial_number: str | None
    status: str
    property_id: str | None
    site_id: str | None
    classification: CommercialClassification


@dataclass(frozen=True)
class AssetOwnership:
    id: str
    tenant_id: str
    asset_id: str
    ownership_kind: OwnershipKind
    customer_id: str | None
    purchased_by: str | None
    maintained_by: str | None
    replacement_responsibility: str | None
    risk_bearer: str | None
    valid_from: str
    valid_until: str | None
    acquisition_document: str | None
    classification: CommercialClassification

    def __post_init__(self) -> None:
        iso_timestamp(self.valid_from)
        if self.valid_until is not None:
            iso_timestamp(self.valid_until)


@dataclass(frozen=True)
class PricingPolicy:
    id: str
    tenant_id: str
    name: str
    scope: str
    status: str
    created_by: str


@dataclass(frozen=True)
class PricingPolicyVersion:
    id: str
    tenant_id: str
    policy_id: str
    version: int
    status: str
    lower_threshold: Decimal
    lower_rate: Decimal
    lower_minimum: Decimal
    upper_rate: Decimal
    upper_minimum: Decimal
    currency: str
    valid_from: str
    valid_until: str | None
    created_by: str
    approved_by: str | None
    classification: CommercialClassification
    source: str

    def __post_init__(self) -> None:
        for value in (
            self.lower_threshold,
            self.lower_rate,
            self.lower_minimum,
            self.upper_rate,
            self.upper_minimum,
        ):
            decimal_value(value)
        iso_timestamp(self.valid_from)
        if self.valid_until is not None:
            iso_timestamp(self.valid_until)


@dataclass(frozen=True)
class CapitalBreakdown:
    capex_ribeira: Decimal | None
    net_installation_margin: Decimal | None
    other_net_inflows: Decimal | None
    capex_classification: CommercialClassification = CommercialClassification.CONFIRMED
    margin_classification: CommercialClassification = CommercialClassification.CONFIRMED
    other_inflows_classification: CommercialClassification = (
        CommercialClassification.CONFIRMED
    )

    def __post_init__(self) -> None:
        for value in (
            self.capex_ribeira,
            self.net_installation_margin,
            self.other_net_inflows,
        ):
            optional_decimal(value)

    def capital_liquido(self) -> Decimal | None:
        if (
            self.capex_ribeira is None
            or self.net_installation_margin is None
            or self.other_net_inflows is None
        ):
            return None
        return (
            self.capex_ribeira - self.net_installation_margin - self.other_net_inflows
        )


@dataclass(frozen=True)
class PricingResult:
    status: PricingStatus
    result: Decimal | None
    currency: str
    inputs: dict[str, Any]
    formula: str
    policy_id: str
    policy_version: int
    classification: CommercialClassification
    assumptions: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    simulation: bool = False


class PricingEngine:
    @staticmethod
    def validate_policy(policy: PricingPolicyVersion) -> None:
        if policy.lower_threshold < 0:
            raise ValueError("pricing threshold cannot be negative")
        boundary = policy.lower_threshold
        lower_price = max(policy.lower_minimum, boundary * policy.lower_rate)
        upper_price = max(
            policy.upper_minimum, (boundary + Decimal("0.01")) * policy.upper_rate
        )
        if upper_price < lower_price:
            raise ValueError(
                "pricing policy violates monotonicity at its band boundary"
            )

    @classmethod
    def calculate(
        cls,
        policy: PricingPolicyVersion,
        capital: CapitalBreakdown,
        *,
        simulation: bool,
    ) -> PricingResult:
        cls.validate_policy(policy)
        missing: list[str] = []
        for name, value in (
            ("capex_ribeira", capital.capex_ribeira),
            ("net_installation_margin", capital.net_installation_margin),
            ("other_net_inflows", capital.other_net_inflows),
        ):
            if value is None:
                missing.append(name)
        capital_value = capital.capital_liquido()
        inputs = {
            "capex_ribeira": capital.capex_ribeira,
            "net_installation_margin": capital.net_installation_margin,
            "other_net_inflows": capital.other_net_inflows,
            "capital_liquido": capital_value,
            "lower_threshold": policy.lower_threshold,
            "lower_rate": policy.lower_rate,
            "lower_minimum": policy.lower_minimum,
            "upper_rate": policy.upper_rate,
            "upper_minimum": policy.upper_minimum,
        }
        assumptions = [
            key
            for key, classification in (
                ("capex_ribeira", capital.capex_classification),
                ("net_installation_margin", capital.margin_classification),
                ("other_net_inflows", capital.other_inflows_classification),
            )
            if classification == CommercialClassification.ASSUMPTION
        ]
        if capital_value is None:
            return PricingResult(
                PricingStatus.INCOMPLETE_PRICING,
                None,
                policy.currency,
                inputs,
                "capital_liquido = capex_ribeira - net_installation_margin - other_net_inflows; price = band(capital_liquido)",
                policy.policy_id,
                policy.version,
                CommercialClassification.UNKNOWN,
                assumptions,
                missing,
                [
                    "essential financial input is missing; NULL was not converted to zero"
                ],
                simulation,
            )
        if capital_value <= policy.lower_threshold:
            price = max(policy.lower_minimum, capital_value * policy.lower_rate)
            formula = "MAX(lower_minimum, capital_liquido × lower_rate)"
        else:
            price = max(policy.upper_minimum, capital_value * policy.upper_rate)
            formula = "MAX(upper_minimum, capital_liquido × upper_rate)"
        return PricingResult(
            PricingStatus.COMPLETE,
            money(price),
            policy.currency,
            inputs,
            formula,
            policy.policy_id,
            policy.version,
            CommercialClassification.SIMULATION
            if simulation
            else CommercialClassification.CALCULATED,
            assumptions,
            [],
            [],
            simulation,
        )


@dataclass(frozen=True)
class OperationalCapacityPolicy:
    id: str
    tenant_id: str
    scope: str
    capacity_type: str
    value: Decimal
    unit: str
    effective_from: str
    effective_until: str | None
    status: str
    created_by: str
    approved_by: str | None
    source: str
    classification: CommercialClassification

    def __post_init__(self) -> None:
        decimal_value(self.value)
        iso_timestamp(self.effective_from)
        if self.effective_until is not None:
            iso_timestamp(self.effective_until)


@dataclass(frozen=True)
class CapacityEvaluation:
    status: CapacityStatus
    requested_capacity: Decimal
    current_capacity: Decimal | None
    difference: Decimal | None
    effective_policy_id: str | None
    evidence_ids: list[str]
    recommended_decision: str
    missing_data: list[str] = field(default_factory=list)


class CapacityEngine:
    @staticmethod
    def evaluate(
        requested_capacity: Decimal,
        policy: OperationalCapacityPolicy | None,
        evidence_ids: list[str] | None = None,
    ) -> CapacityEvaluation:
        requested = decimal_value(requested_capacity)
        evidence = list(evidence_ids or [])
        if policy is None:
            return CapacityEvaluation(
                CapacityStatus.UNKNOWN,
                requested,
                None,
                None,
                None,
                evidence,
                "do not continue planning until an active capacity policy is confirmed",
                ["active operational capacity policy"],
            )
        difference = requested - policy.value
        if requested > policy.value:
            status = CapacityStatus.CAPACITY_GATE_REQUIRED
            decision = "request capacity expansion decision; do not increase capacity automatically"
        elif requested == policy.value:
            status = CapacityStatus.AT_CAPACITY
            decision = "review operational risk before accepting additional work"
        else:
            status = CapacityStatus.WITHIN_CAPACITY
            decision = "capacity is within the active policy"
        return CapacityEvaluation(
            status,
            requested,
            policy.value,
            difference,
            policy.id,
            evidence,
            decision,
        )


@dataclass(frozen=True)
class CommercialConditionResult:
    state: ConditionState
    evidence_ids: list[str]
    unknown_factors: list[str]
    matched_factors: list[str]


class CommercialRuleEngine:
    """Small three-valued evaluator; missing facts never become false."""

    @classmethod
    def evaluate(
        cls, condition: dict[str, Any], facts: dict[str, Any]
    ) -> CommercialConditionResult:
        state, evidence, unknown, matched = cls._evaluate(condition, facts)
        return CommercialConditionResult(
            state,
            sorted(set(evidence)),
            sorted(set(unknown)),
            sorted(set(matched)),
        )

    @classmethod
    def _evaluate(
        cls, condition: dict[str, Any], facts: dict[str, Any]
    ) -> tuple[ConditionState, list[str], list[str], list[str]]:
        if "all" in condition:
            children = [cls._evaluate(item, facts) for item in condition["all"]]
            return cls._combine_all(children)
        if "any" in condition:
            children = [cls._evaluate(item, facts) for item in condition["any"]]
            return cls._combine_any(children)
        fact_name = condition.get("fact")
        if not isinstance(fact_name, str):
            raise ValueError("commercial condition requires a fact")
        value = facts.get(fact_name)
        evidence = [str(item) for item in condition.get("evidence_ids", [])]
        if value is None:
            return ConditionState.UNKNOWN, evidence, [fact_name], []
        operator = condition.get("operator", "eq")
        expected = condition.get("value")
        try:
            if operator == "eq":
                matched = value == expected
            elif operator == "neq":
                matched = value != expected
            elif operator in {"gt", "gte", "lt", "lte"}:
                left, right = Decimal(str(value)), Decimal(str(expected))
                matched = {
                    "gt": left > right,
                    "gte": left >= right,
                    "lt": left < right,
                    "lte": left <= right,
                }[operator]
            elif operator == "is_true":
                matched = value is True
            elif operator == "is_false":
                matched = value is False
            else:
                raise ValueError(f"unsupported commercial operator: {operator}")
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"invalid commercial condition for {fact_name}") from exc
        return (
            ConditionState.TRUE if matched else ConditionState.FALSE,
            evidence,
            [],
            [fact_name] if matched else [],
        )

    @staticmethod
    def _combine_all(
        children: list[tuple[ConditionState, list[str], list[str], list[str]]],
    ) -> tuple[ConditionState, list[str], list[str], list[str]]:
        return CommercialRuleEngine._combine(
            children, ConditionState.TRUE, all_mode=True
        )

    @staticmethod
    def _combine_any(
        children: list[tuple[ConditionState, list[str], list[str], list[str]]],
    ) -> tuple[ConditionState, list[str], list[str], list[str]]:
        return CommercialRuleEngine._combine(
            children, ConditionState.FALSE, all_mode=False
        )

    @staticmethod
    def _combine(
        children: list[tuple[ConditionState, list[str], list[str], list[str]]],
        neutral: ConditionState,
        *,
        all_mode: bool,
    ) -> tuple[ConditionState, list[str], list[str], list[str]]:
        states = [item[0] for item in children]
        evidence = [value for item in children for value in item[1]]
        unknown = [value for item in children for value in item[2]]
        matched = [value for item in children for value in item[3]]
        if not children:
            return neutral, evidence, unknown, matched
        if all_mode:
            if ConditionState.FALSE in states:
                state = ConditionState.FALSE
            elif ConditionState.UNKNOWN in states:
                state = ConditionState.UNKNOWN
            else:
                state = ConditionState.TRUE
        elif ConditionState.TRUE in states:
            state = ConditionState.TRUE
        elif ConditionState.UNKNOWN in states:
            state = ConditionState.UNKNOWN
        else:
            state = ConditionState.FALSE
        return state, evidence, unknown, matched


@dataclass(frozen=True)
class CommercialOpportunity:
    id: str
    tenant_id: str
    customer_id: str
    property_id: str | None
    opportunity_type: str
    status: OpportunityStatus
    classification: OpportunityClassification
    score: Decimal | None
    evidence_ids: list[str]
    rule_id: str | None
    rule_version: int | None
    estimated_value: Decimal | None
    estimated_value_classification: CommercialClassification
    created_at: str | None = None
    closed_at: str | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class ProspectScoringFactor:
    id: str
    tenant_id: str
    model_version_id: str
    factor_key: str
    description: str
    condition: dict[str, Any]
    points: int
    unknown_policy: str
    status: str


@dataclass(frozen=True)
class ProspectScoringModelVersion:
    id: str
    tenant_id: str
    model_id: str
    version: int
    status: str
    unknown_policy: str
    valid_from: str
    valid_until: str | None
    created_by: str
    approved_by: str | None


@dataclass(frozen=True)
class ProspectScoreResult:
    score: Decimal | None
    model_version_id: str
    positive_factors: list[dict[str, Any]]
    negative_factors: list[dict[str, Any]]
    unknown_factors: list[dict[str, Any]]
    evidence_ids: list[str]


class ProspectScoringEngine:
    @staticmethod
    def calculate(
        model: ProspectScoringModelVersion,
        factors: list[ProspectScoringFactor],
        facts: dict[str, Any],
    ) -> ProspectScoreResult:
        score = Decimal("0")
        blocked = False
        positive: list[dict[str, Any]] = []
        negative: list[dict[str, Any]] = []
        unknown: list[dict[str, Any]] = []
        evidence: list[str] = []
        for factor in factors:
            result = CommercialRuleEngine.evaluate(factor.condition, facts)
            if result.state == ConditionState.TRUE:
                entry = {"factor": factor.factor_key, "points": factor.points}
                (positive if factor.points >= 0 else negative).append(entry)
                score += Decimal(factor.points)
                evidence.extend(result.evidence_ids)
            elif result.state == ConditionState.UNKNOWN:
                entry = {
                    "factor": factor.factor_key,
                    "missing": result.unknown_factors,
                    "policy": factor.unknown_policy,
                }
                unknown.append(entry)
                if factor.unknown_policy == "PENALIZE":
                    score -= Decimal(abs(factor.points))
                elif (
                    factor.unknown_policy == "BLOCK" or model.unknown_policy == "BLOCK"
                ):
                    blocked = True
        return ProspectScoreResult(
            None if blocked else score,
            model.id,
            positive,
            negative,
            unknown,
            sorted(set(evidence)),
        )
