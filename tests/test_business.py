from __future__ import annotations

import unittest
from decimal import Decimal

from ribeira_platform.business import (
    CapacityEngine,
    CapacityStatus,
    CapitalBreakdown,
    CommercialClassification,
    CommercialRuleEngine,
    ConditionState,
    ContractVersion,
    CustomerContract,
    InstallationProject,
    OperationalCapacityPolicy,
    OpportunityStatus,
    PassThroughItem,
    PricingEngine,
    PricingPolicy,
    PricingPolicyVersion,
    PricingStatus,
    RevenueTreatment,
    ServiceOffering,
    ServicePlan,
    Subscription,
    ProductStatus,
    RevenueType,
)
from ribeira_platform.models import new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.sources import SyntheticFixtureAdapter
from ribeira_platform.storage import SQLiteStore


class BusinessDomainTests(unittest.TestCase):
    def test_pricing_is_decimal_monotonic_and_transparent(self) -> None:
        policy = PricingPolicyVersion(
            new_id(),
            "tenant",
            new_id(),
            1,
            "ACTIVE",
            Decimal("10000"),
            Decimal("0.15"),
            Decimal("500"),
            Decimal("0.12"),
            Decimal("1500"),
            "BRL",
            "2026-09-16T00:00:00+00:00",
            None,
            "creator",
            "approver",
            CommercialClassification.CONFIRMED,
            "confirmed historical policy",
        )
        previous = Decimal("0")
        for value in range(0, 100001, 137):
            result = PricingEngine.calculate(
                policy,
                CapitalBreakdown(Decimal(value), Decimal("0"), Decimal("0")),
                simulation=True,
            )
            self.assertEqual(result.status, PricingStatus.COMPLETE)
            self.assertIsNotNone(result.result)
            self.assertGreaterEqual(result.result, previous)
            previous = result.result
            self.assertEqual(result.currency, "BRL")
            self.assertTrue(result.simulation)
            self.assertEqual(result.classification, CommercialClassification.SIMULATION)

    def test_pricing_does_not_turn_missing_input_into_zero(self) -> None:
        policy = PricingPolicyVersion(
            new_id(),
            "tenant",
            new_id(),
            1,
            "ACTIVE",
            Decimal("10000"),
            Decimal("0.15"),
            Decimal("500"),
            Decimal("0.12"),
            Decimal("1500"),
            "BRL",
            "2026-09-16T00:00:00+00:00",
            None,
            "creator",
            "approver",
            CommercialClassification.CONFIRMED,
            "confirmed historical policy",
        )
        result = PricingEngine.calculate(
            policy,
            CapitalBreakdown(Decimal("1000"), None, Decimal("0")),
            simulation=True,
        )
        self.assertEqual(result.status, PricingStatus.INCOMPLETE_PRICING)
        self.assertIsNone(result.result)
        self.assertIn("net_installation_margin", result.missing_data)
        with self.assertRaises(ValueError):
            CapitalBreakdown(Decimal("-1"), Decimal("0"), Decimal("0"))
        with self.assertRaises(ValueError):
            CapitalBreakdown(Decimal("NaN"), Decimal("0"), Decimal("0"))

    def test_capacity_gate_never_expands_capacity(self) -> None:
        policy = OperationalCapacityPolicy(
            new_id(),
            "tenant",
            "TENANT",
            "INSTALLATIONS_PER_MONTH",
            Decimal("10"),
            "INSTALLATIONS/MONTH",
            "2026-01-01T00:00:00+00:00",
            None,
            "ACTIVE",
            "creator",
            "approver",
            "CURRENT_CONFIRMED_RULE",
            CommercialClassification.CONFIRMED,
        )
        result = CapacityEngine.evaluate(Decimal("11"), policy)
        self.assertEqual(result.status, CapacityStatus.CAPACITY_GATE_REQUIRED)
        self.assertEqual(result.current_capacity, Decimal("10"))
        self.assertEqual(result.difference, Decimal("1"))
        self.assertIn(
            "do not increase capacity automatically", result.recommended_decision
        )
        self.assertEqual(
            CapacityEngine.evaluate(Decimal("10"), policy).status,
            CapacityStatus.AT_CAPACITY,
        )
        self.assertEqual(
            CapacityEngine.evaluate(Decimal("9"), policy).status,
            CapacityStatus.WITHIN_CAPACITY,
        )

    def test_rule_engine_preserves_unknown_and_requires_evidence_for_opportunity(
        self,
    ) -> None:
        condition = {
            "all": [
                {
                    "fact": "customer.current",
                    "operator": "eq",
                    "value": True,
                    "evidence_ids": ["e1"],
                },
                {
                    "fact": "cctv.status",
                    "operator": "eq",
                    "value": "CONFIRMED_ABSENT",
                    "evidence_ids": ["e2"],
                },
            ]
        }
        unknown = CommercialRuleEngine.evaluate(condition, {"customer.current": True})
        self.assertEqual(unknown.state, ConditionState.UNKNOWN)
        self.assertEqual(unknown.unknown_factors, ["cctv.status"])
        explicit_false = CommercialRuleEngine.evaluate(
            condition, {"customer.current": True, "cctv.status": "CONFIRMED_PRESENT"}
        )
        self.assertEqual(explicit_false.state, ConditionState.FALSE)

    def test_business_application_keeps_evidence_chain_and_mrr_rules(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Commercial tenant")
        customer = app.business.create_customer(
            tenant.id, "Customer", actor="commercial"
        )
        property = app.create_property(tenant.id, "Property")
        source = app.create_source(tenant.id, "Fixture", "TEST", "fixture")
        app.adapters[source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.4,
                    "unit": "%",
                    "observation_timestamp": "2026-09-16T13:42:11-03:00",
                }
            ]
        )
        ingestion = app.ingest(tenant.id, property.id, source.id)
        rule_id, _ = app.business.create_commercial_rule_version(
            tenant.id,
            "Security evaluation",
            {
                "all": [
                    {
                        "fact": "cctv.status",
                        "operator": "eq",
                        "value": "CONFIRMED_ABSENT",
                        "evidence_ids": ingestion.evidence_ids,
                    }
                ]
            },
            {"opportunity_type": "POTENTIAL_CCTV_OPPORTUNITY"},
            created_by="creator",
            approved_by="approver",
            status="ACTIVE",
        )
        qualified = app.business.qualify_opportunity(
            tenant.id,
            customer.id,
            property.id,
            rule_id,
            {"cctv.status": "CONFIRMED_ABSENT"},
            actor="seller",
        )
        self.assertEqual(qualified.status, "QUALIFIED")
        self.assertEqual(qualified.opportunity.status, OpportunityStatus.OPEN)
        self.assertEqual(qualified.opportunity.evidence_ids, ingestion.evidence_ids)

        service = app.business.create_service(
            ServiceOffering(
                new_id(),
                tenant.id,
                "Managed network",
                "CONNECTIVITY",
                ProductStatus.ACTIVE,
                True,
                RevenueType.RECURRING_REVENUE,
                None,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial",
        )
        plan = app.business.create_service_plan(
            ServicePlan(
                new_id(),
                tenant.id,
                service.id,
                "Managed monthly",
                "MONTH",
                Decimal("250"),
                "BRL",
                "ACTIVE",
                RevenueTreatment.RIBEIRA_RECURRING,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial",
        )
        contract = app.business.create_contract(
            CustomerContract(
                new_id(),
                tenant.id,
                customer.id,
                property.id,
                "RIBEIRA_SERVICE",
                "Ribeira",
                None,
                RevenueTreatment.RIBEIRA_RECURRING,
                "ACTIVE",
                "2026-09-16T00:00:00+00:00",
                None,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial",
        )
        version = app.business.create_contract_version(
            ContractVersion(
                new_id(),
                tenant.id,
                contract.id,
                1,
                "DRAFT",
                "2026-09-16T00:00:00+00:00",
                None,
                Decimal("250"),
                "BRL",
                True,
                {},
                "creator",
                None,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial",
        )
        app.business.create_subscription(
            Subscription(
                new_id(),
                tenant.id,
                contract.id,
                version.id,
                plan.id,
                "ACTIVE",
                "2026-09-16T00:00:00+00:00",
                None,
                Decimal("250"),
                "BRL",
                True,
                True,
                RevenueTreatment.RIBEIRA_RECURRING,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial",
        )
        pass_through = PassThroughItem(
            new_id(),
            tenant.id,
            None,
            customer.id,
            "CFTV hardware",
            Decimal("1000"),
            "BRL",
            "Vendor",
            "DOC-1",
            None,
            CommercialClassification.CONFIRMED,
        )
        app.business.register_pass_through_item(pass_through, actor="commercial")
        mrr = app.business.calculate_mrr(tenant.id, customer.id)
        self.assertEqual(mrr["result"], Decimal("250"))
        self.assertNotIn("pass_through", str(mrr["components"]))
        store.close()

    def test_external_link_and_external_consultant_are_not_ribeira_revenue(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            CustomerContract(
                new_id(),
                "tenant",
                "customer",
                None,
                "EXTERNAL_LINK",
                "ISP",
                "ISP",
                RevenueTreatment.RIBEIRA_RECURRING,
                "ACTIVE",
                "2026-09-16T00:00:00+00:00",
                None,
                CommercialClassification.CONFIRMED,
            )
        with self.assertRaises(ValueError):
            InstallationProject(
                new_id(),
                "tenant",
                "customer",
                None,
                "External project",
                "DRAFT",
                "EXTERNAL_CONSULTANT",
                Decimal("1000"),
                "BRL",
                RevenueTreatment.RIBEIRA_ONE_TIME,
                CommercialClassification.CONFIRMED,
            )

    def test_business_version_approval_uses_authenticated_approver(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Approval tenant")
        policy = app.business.create_pricing_policy(
            PricingPolicy(
                new_id(),
                tenant.id,
                "Managed infrastructure",
                "TENANT",
                "DRAFT",
                "creator",
            ),
            actor="creator",
        )
        version = app.business.create_pricing_policy_version(
            PricingPolicyVersion(
                new_id(),
                tenant.id,
                policy.id,
                1,
                "DRAFT",
                Decimal("10000"),
                Decimal("0.15"),
                Decimal("500"),
                Decimal("0.12"),
                Decimal("1500"),
                "BRL",
                "2026-09-16T00:00:00+00:00",
                None,
                "creator",
                None,
                CommercialClassification.CONFIRMED,
                "confirmed policy source",
            ),
            actor="creator",
        )
        with self.assertRaises(ValueError):
            app.business.approve_pricing_policy_version(
                tenant.id, policy.id, version.id, approver="creator"
            )
        app.business.approve_pricing_policy_version(
            tenant.id, policy.id, version.id, approver="approver"
        )
        row = store.connection.execute(
            "SELECT status, approved_by FROM pricing_policy_version WHERE id=?",
            (version.id,),
        ).fetchone()
        self.assertEqual(row["status"], "ACTIVE")
        self.assertEqual(row["approved_by"], "approver")
        store.close()


if __name__ == "__main__":
    unittest.main()
