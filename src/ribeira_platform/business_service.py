from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .business import (
    Asset,
    AssetOwnership,
    CapexItem,
    CapacityEngine,
    CapacityEvaluation,
    CapitalBreakdown,
    CommercialClassification,
    CommercialConditionResult,
    ConditionState,
    CommercialOpportunity,
    CommercialRuleEngine,
    ContractVersion,
    Customer,
    CustomerContract,
    InstallationProject,
    OpportunityClassification,
    OpportunityStatus,
    OperationalCapacityPolicy,
    PricingEngine,
    PricingPolicy,
    PricingPolicyVersion,
    PricingResult,
    PricingStatus,
    Product,
    PassThroughItem,
    RevenueTreatment,
    ServiceOffering,
    ServicePlan,
    Subscription,
    ProspectScoringFactor,
    ProspectScoringModelVersion,
    ProspectScoringEngine,
    ProspectScoreResult,
)
from .business_repository import BusinessRepository
from .epistemology import DataClassification
from .models import Evidence, new_id, now_utc
from .time_utils import parse_aware


@dataclass(frozen=True)
class OpportunityQualification:
    condition: CommercialConditionResult
    opportunity: CommercialOpportunity | None
    status: str
    missing_data: list[str]


class BusinessApplication:
    """Use cases for Ribeira's commercial/business domain."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.repository = BusinessRepository(store)

    def _audit(
        self,
        tenant_id: str,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.store.audit(
            tenant_id,
            actor,
            event_type,
            entity_type,
            entity_id,
            payload,
            new_id(),
            now_utc(),
        )

    @staticmethod
    def _asset_evidence_classification(
        classification: CommercialClassification,
    ) -> DataClassification:
        """Translate the business-record classification without inventing facts."""
        mapping = {
            CommercialClassification.CONFIRMED: DataClassification.MANUAL_CONFIRMED,
            CommercialClassification.OBSERVED: DataClassification.OBSERVED,
            CommercialClassification.MANUAL_CONFIRMED: DataClassification.MANUAL_CONFIRMED,
            CommercialClassification.CALCULATED: DataClassification.CALCULATED,
            CommercialClassification.ASSUMPTION: DataClassification.ASSUMPTION,
            CommercialClassification.SIMULATION: DataClassification.SIMULATED,
            CommercialClassification.UNKNOWN: DataClassification.UNKNOWN,
        }
        return mapping[classification]

    def _evidence_for_registered_asset(self, item: Asset) -> Evidence:
        """Persist factual asset-record evidence without inferring operational state."""
        existing = self.store.evidence_for_reference(item.tenant_id, item.id)
        if existing is not None:
            return existing
        return self.store.create_evidence(
            Evidence(
                id=new_id(),
                tenant_id=item.tenant_id,
                evidence_type="ASSET_REGISTRATION",
                reference_id=item.id,
                classification=self._asset_evidence_classification(item.classification),
                source_id=None,
                observed_at=item.observed_at,
                transformation="asset registration retained as submitted; no location, condition, ownership, calibration, connectivity, or service availability was inferred",
                limitations=[
                    "the record establishes only the submitted asset facts and their stated source reference",
                    "it is not a measurement, independent verification, diagnosis, coverage assessment, or service-availability claim",
                ],
            )
        )

    def create_customer(
        self,
        tenant_id: str,
        display_name: str,
        *,
        customer_type: str = "LEGAL_ENTITY",
        legal_name: str | None = None,
        status: str = "ACTIVE",
        external_reference: str | None = None,
        actor: str = "system",
        platform_admin: bool = False,
        customer_id: str | None = None,
    ) -> Customer:
        item = Customer(
            customer_id or new_id(),
            tenant_id,
            customer_type,
            display_name,
            legal_name,
            status,
            CommercialClassification.CONFIRMED,
            external_reference,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.create_customer(item)
            self._audit(
                tenant_id,
                actor,
                "CUSTOMER_CREATED",
                "customer",
                item.id,
                {"classification": item.classification.value},
            )
        return item

    def link_customer_property(
        self,
        tenant_id: str,
        customer_id: str,
        property_id: str,
        relationship_type: str,
        valid_from: str,
        valid_until: str | None,
        actor: str,
        link_id: str | None = None,
    ) -> str:
        parse_aware(valid_from)
        if valid_until is not None:
            parse_aware(valid_until)
        with self.store.tenant_transaction(tenant_id):
            item_id = self.repository.create_customer_property(
                tenant_id,
                customer_id,
                property_id,
                relationship_type,
                valid_from,
                valid_until,
                CommercialClassification.CONFIRMED,
                link_id,
            )
            self._audit(
                tenant_id,
                actor,
                "CUSTOMER_PROPERTY_LINKED",
                "customer_property",
                item_id,
                {"customer_id": customer_id, "property_id": property_id},
            )
            return item_id

    def create_contract(
        self,
        item: CustomerContract,
        *,
        actor: str,
        platform_admin: bool = False,
    ) -> CustomerContract:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_contract(item)
            self._audit(
                item.tenant_id,
                actor,
                "CONTRACT_CREATED",
                "customer_contract",
                item.id,
                {
                    "contract_type": item.contract_type,
                    "revenue_treatment": item.revenue_treatment.value,
                },
            )
        return item

    def create_contract_version(
        self, item: ContractVersion, *, actor: str, platform_admin: bool = False
    ) -> ContractVersion:
        if item.status == "ACTIVE" and (
            not item.approved_by or item.approved_by == item.created_by
        ):
            raise ValueError("active contract version requires a distinct approver")
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_contract_version(item)
            self._audit(
                item.tenant_id,
                actor,
                "CONTRACT_VERSION_CREATED",
                "contract_version",
                item.id,
                {
                    "contract_id": item.contract_id,
                    "version": item.version,
                    "status": item.status,
                },
            )
        return item

    def approve_contract_version(
        self,
        tenant_id: str,
        version_id: str,
        *,
        approver: str,
        platform_admin: bool = False,
    ) -> None:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.approve_version(
                "contract_version", tenant_id, version_id, approver
            )
            self._audit(
                tenant_id,
                approver,
                "CONTRACT_VERSION_APPROVED",
                "contract_version",
                version_id,
                {"approved_by": approver},
            )

    def create_product(
        self, item: Product, *, actor: str, platform_admin: bool = False
    ) -> Product:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_product(item)
            self._audit(
                item.tenant_id,
                actor,
                "PRODUCT_CREATED",
                "product",
                item.id,
                {"status": item.status.value},
            )
        return item

    def create_service(
        self, item: ServiceOffering, *, actor: str, platform_admin: bool = False
    ) -> ServiceOffering:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_service(item)
            self._audit(
                item.tenant_id,
                actor,
                "SERVICE_CREATED",
                "service",
                item.id,
                {"recurring": item.recurring, "revenue_type": item.revenue_type.value},
            )
        return item

    def create_service_plan(
        self, item: ServicePlan, *, actor: str, platform_admin: bool = False
    ) -> ServicePlan:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_service_plan(item)
            self._audit(
                item.tenant_id,
                actor,
                "SERVICE_PLAN_CREATED",
                "service_plan",
                item.id,
                {"revenue_treatment": item.revenue_treatment.value},
            )
        return item

    def create_subscription(
        self, item: Subscription, *, actor: str, platform_admin: bool = False
    ) -> Subscription:
        if item.revenue_treatment == RevenueTreatment.CUSTOMER_DIRECT_EXTERNAL:
            raise ValueError(
                "customer-direct external subscriptions are not Ribeira revenue subscriptions"
            )
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_subscription(item)
            self._audit(
                item.tenant_id,
                actor,
                "SUBSCRIPTION_CREATED",
                "subscription",
                item.id,
                {
                    "mrr_eligible": item.mrr_eligible,
                    "recurring": item.recurring,
                    "revenue_treatment": item.revenue_treatment.value,
                },
            )
        return item

    def calculate_mrr(
        self, tenant_id: str, customer_id: str, *, platform_admin: bool = False
    ) -> dict[str, Any]:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            return self.repository.calculate_mrr(tenant_id, customer_id)

    def register_asset(
        self, item: Asset, *, actor: str, platform_admin: bool = False
    ) -> Asset:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            if (
                item.property_id is not None
                and self.store.get_property(item.tenant_id, item.property_id) is None
            ):
                raise LookupError("asset property is unavailable in tenant")
            self.repository.create_asset(item)
            evidence = self._evidence_for_registered_asset(item)
            self._audit(
                item.tenant_id,
                actor,
                "ASSET_REGISTERED",
                "asset",
                item.id,
                {
                    "asset_type": item.asset_type,
                    "classification": item.classification.value,
                    "evidence_id": evidence.id,
                    "source_reference_recorded": item.source_reference is not None,
                    "observed_at": item.observed_at,
                },
            )
        return item

    def asset_for_rule_evaluation(
        self, tenant_id: str, asset_id: str, *, platform_admin: bool = False
    ) -> Asset:
        """Resolve only a tenant-local asset that is explicitly linked to a property.

        Property observations may be evaluated with this asset as declared
        context, but the asset itself is never treated as a measurement.
        """
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.repository.get_asset(tenant_id, asset_id)
            if item is None:
                raise LookupError("asset not found in tenant")
            if item.property_id is None:
                raise ValueError(
                    "asset rule evaluation requires an associated property"
                )
            if self.store.get_property(tenant_id, item.property_id) is None:
                raise LookupError("asset property is unavailable in tenant")
            return item

    def list_assets_for_property(
        self, tenant_id: str, property_id: str, *, platform_admin: bool = False
    ) -> list[Asset]:
        """Read a property inventory without crossing tenant or property scope."""
        with self.store.tenant_transaction(tenant_id, platform_admin):
            if self.store.get_property(tenant_id, property_id) is None:
                raise LookupError("property not found in tenant")
            return self.repository.list_assets_for_property(tenant_id, property_id)

    def assign_asset_ownership(
        self, item: AssetOwnership, *, actor: str, platform_admin: bool = False
    ) -> AssetOwnership:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_asset_ownership(item)
            self._audit(
                item.tenant_id,
                actor,
                "ASSET_OWNERSHIP_ASSIGNED",
                "asset_ownership",
                item.id,
                {
                    "asset_id": item.asset_id,
                    "ownership_kind": item.ownership_kind.value,
                },
            )
        return item

    def create_installation_project(
        self, item: InstallationProject, *, actor: str, platform_admin: bool = False
    ) -> InstallationProject:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_installation_project(item)
            self._audit(
                item.tenant_id,
                actor,
                "INSTALLATION_PROJECT_CREATED",
                "installation_project",
                item.id,
                {
                    "technical_provider_type": item.technical_provider_type,
                    "revenue_treatment": item.revenue_treatment.value,
                },
            )
        return item

    def register_capex_item(
        self, item: CapexItem, *, actor: str, platform_admin: bool = False
    ) -> CapexItem:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_capex_item(item)
            self._audit(
                item.tenant_id,
                actor,
                "CAPEX_ITEM_REGISTERED",
                "capex_item",
                item.id,
                {
                    "classification": item.capex_classification.value,
                    "ownership_kind": item.ownership_kind.value,
                },
            )
        return item

    def register_pass_through_item(
        self, item: PassThroughItem, *, actor: str, platform_admin: bool = False
    ) -> PassThroughItem:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_pass_through_item(item)
            self._audit(
                item.tenant_id,
                actor,
                "PASS_THROUGH_REGISTERED",
                "pass_through_item",
                item.id,
                {"classification": item.classification.value},
            )
        return item

    def create_pricing_policy(
        self, item: PricingPolicy, *, actor: str, platform_admin: bool = False
    ) -> PricingPolicy:
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_pricing_policy(item)
            self._audit(
                item.tenant_id,
                actor,
                "PRICING_POLICY_CREATED",
                "pricing_policy",
                item.id,
                {"scope": item.scope},
            )
        return item

    def create_pricing_policy_version(
        self, item: PricingPolicyVersion, *, actor: str, platform_admin: bool = False
    ) -> PricingPolicyVersion:
        PricingEngine.validate_policy(item)
        if item.status == "ACTIVE" and (
            not item.approved_by or item.approved_by == item.created_by
        ):
            raise ValueError("active pricing policy requires a distinct approver")
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_pricing_policy_version(item)
            self._audit(
                item.tenant_id,
                actor,
                "PRICING_POLICY_VERSION_CREATED",
                "pricing_policy_version",
                item.id,
                {
                    "policy_id": item.policy_id,
                    "version": item.version,
                    "status": item.status,
                    "created_by": item.created_by,
                    "approved_by": item.approved_by,
                },
            )
        return item

    def approve_pricing_policy_version(
        self,
        tenant_id: str,
        policy_id: str,
        version_id: str,
        *,
        approver: str,
        platform_admin: bool = False,
    ) -> None:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.approve_version(
                "pricing_policy_version",
                tenant_id,
                version_id,
                approver,
                "pricing_policy_id",
                policy_id,
            )
            self._audit(
                tenant_id,
                approver,
                "PRICING_POLICY_VERSION_APPROVED",
                "pricing_policy_version",
                version_id,
                {"approved_by": approver},
            )

    def simulate_price(
        self,
        tenant_id: str,
        policy_id: str,
        capital: CapitalBreakdown,
        *,
        version: int | None = None,
        platform_admin: bool = False,
    ) -> PricingResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            policy = self.repository.get_pricing_policy_version(
                tenant_id, policy_id, version
            )
            if policy is None:
                return PricingResult(
                    PricingStatus.INCOMPLETE_PRICING,
                    None,
                    "BRL",
                    {},
                    "active pricing policy version not found",
                    policy_id,
                    version or 0,
                    CommercialClassification.UNKNOWN,
                    missing_data=["active_pricing_policy_version"],
                    simulation=True,
                )
            return PricingEngine.calculate(policy, capital, simulation=True)

    def create_capacity_policy(
        self,
        item: OperationalCapacityPolicy,
        *,
        actor: str,
        platform_admin: bool = False,
    ) -> OperationalCapacityPolicy:
        if item.status == "ACTIVE" and (
            not item.approved_by or item.approved_by == item.created_by
        ):
            raise ValueError("active capacity policy requires a distinct approver")
        with self.store.tenant_transaction(item.tenant_id, platform_admin):
            self.repository.create_capacity_policy(item)
            self._audit(
                item.tenant_id,
                actor,
                "CAPACITY_POLICY_CREATED",
                "operational_capacity_policy",
                item.id,
                {
                    "capacity_type": item.capacity_type,
                    "value": item.value,
                    "unit": item.unit,
                    "status": item.status,
                },
            )
        return item

    def approve_capacity_policy(
        self,
        tenant_id: str,
        policy_id: str,
        *,
        approver: str,
        platform_admin: bool = False,
    ) -> None:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.approve_version(
                "operational_capacity_policy", tenant_id, policy_id, approver
            )
            self._audit(
                tenant_id,
                approver,
                "CAPACITY_POLICY_APPROVED",
                "operational_capacity_policy",
                policy_id,
                {"approved_by": approver},
            )

    def evaluate_capacity(
        self,
        tenant_id: str,
        requested_capacity: Decimal,
        capacity_type: str,
        *,
        evidence_ids: list[str] | None = None,
        platform_admin: bool = False,
    ) -> CapacityEvaluation:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            policy = self.repository.active_capacity_policy(
                tenant_id, capacity_type, now_utc()
            )
            return CapacityEngine.evaluate(requested_capacity, policy, evidence_ids)

    def create_commercial_rule_version(
        self,
        tenant_id: str,
        name: str,
        condition: dict[str, Any],
        action: dict[str, Any],
        *,
        created_by: str,
        approved_by: str | None,
        version: int = 1,
        status: str = "DRAFT",
        platform_admin: bool = False,
    ) -> tuple[str, str]:
        rule_id, version_id = new_id(), new_id()
        if status == "ACTIVE" and (not approved_by or approved_by == created_by):
            raise ValueError("active commercial rule requires a distinct approver")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.create_commercial_rule(
                rule_id, tenant_id, name, "REGRA_COMERCIAL", status, created_by
            )
            self.repository.create_commercial_rule_version(
                version_id,
                tenant_id,
                rule_id,
                version,
                condition,
                action,
                status,
                now_utc(),
                None,
                created_by,
                approved_by,
                CommercialClassification.CONFIRMED,
            )
            self._audit(
                tenant_id,
                created_by,
                "COMMERCIAL_RULE_VERSION_CREATED",
                "commercial_rule_version",
                version_id,
                {"rule_id": rule_id, "version": version, "status": status},
            )
        return rule_id, version_id

    def approve_commercial_rule_version(
        self,
        tenant_id: str,
        version_id: str,
        *,
        approver: str,
        platform_admin: bool = False,
    ) -> None:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.approve_version(
                "commercial_rule_version", tenant_id, version_id, approver
            )
            self._audit(
                tenant_id,
                approver,
                "COMMERCIAL_RULE_VERSION_APPROVED",
                "commercial_rule_version",
                version_id,
                {"approved_by": approver},
            )

    def qualify_opportunity(
        self,
        tenant_id: str,
        customer_id: str,
        property_id: str | None,
        rule_id: str,
        facts: dict[str, Any],
        *,
        version: int | None = None,
        actor: str,
        classification: OpportunityClassification = OpportunityClassification.POTENTIAL_OPPORTUNITY,
        platform_admin: bool = False,
    ) -> OpportunityQualification:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            rule = self.repository.get_commercial_rule_version(
                tenant_id, rule_id, version
            )
            if rule is None:
                return OpportunityQualification(
                    CommercialConditionResult(
                        ConditionState.UNKNOWN, [], ["active_commercial_rule"], []
                    ),
                    None,
                    "INCONCLUSIVE",
                    ["active_commercial_rule"],
                )
            result = CommercialRuleEngine.evaluate(rule["condition"], facts)
            if result.state != ConditionState.TRUE:
                return OpportunityQualification(
                    result,
                    None,
                    "INCONCLUSIVE"
                    if result.state == ConditionState.UNKNOWN
                    else "NOT_APPLICABLE",
                    result.unknown_factors,
                )
            evidence_ids = sorted(set(result.evidence_ids))
            if not evidence_ids or any(
                not self.repository.evidence_exists(tenant_id, item)
                for item in evidence_ids
            ):
                return OpportunityQualification(
                    result,
                    None,
                    "INCONCLUSIVE",
                    ["valid_evidence_for_commercial_conclusion"],
                )
            opportunity = CommercialOpportunity(
                new_id(),
                tenant_id,
                customer_id,
                property_id,
                rule["action"].get("opportunity_type", "UNSPECIFIED"),
                OpportunityStatus.OPEN,
                classification,
                None,
                evidence_ids,
                rule_id,
                rule["version"],
                None,
                CommercialClassification.UNKNOWN,
            )
            self.repository.create_opportunity(opportunity)
            for evidence_id in evidence_ids:
                self.repository.create_opportunity_evidence(
                    tenant_id, opportunity.id, evidence_id, "RULE_SUPPORT"
                )
            self._audit(
                tenant_id,
                actor,
                "COMMERCIAL_OPPORTUNITY_CREATED",
                "commercial_opportunity",
                opportunity.id,
                {
                    "rule_id": rule_id,
                    "rule_version": rule["version"],
                    "evidence_ids": evidence_ids,
                    "classification": classification.value,
                },
            )
            return OpportunityQualification(result, opportunity, "QUALIFIED", [])

    @staticmethod
    def score_prospect(
        model: ProspectScoringModelVersion,
        factors: list[ProspectScoringFactor],
        facts: dict[str, Any],
    ) -> ProspectScoreResult:
        return ProspectScoringEngine.calculate(model, factors, facts)
