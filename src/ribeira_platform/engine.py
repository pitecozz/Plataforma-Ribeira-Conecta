from __future__ import annotations

from collections import defaultdict
from typing import Any

from .epistemology import DataClassification, DecisionStatus, QualityFlag
from .models import (
    Action,
    Alert,
    Decision,
    DecisionResult,
    Evidence,
    Observation,
    Property,
    RuleDefinition,
    new_id,
    now_utc,
)
from .storage import SQLiteStore


class EvidenceEngine:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def evidence_for_observation(self, observation: Observation) -> Evidence:
        existing = self.store.evidence_for_reference(
            observation.tenant_id, observation.id
        )
        if existing is not None:
            return existing
        return self.store.create_evidence(
            Evidence(
                id=new_id(),
                tenant_id=observation.tenant_id,
                evidence_type="OBSERVATION",
                reference_id=observation.id,
                classification=observation.classification,
                source_id=observation.source_id,
                observed_at=observation.observation_timestamp,
                transformation="canonical observation persisted without imputation",
                limitations=[
                    "sensor/source quality is not independently validated by this slice"
                ],
            )
        )


class DecisionEngine:
    """Deterministic, explainable rule evaluation for the first slice."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.evidence = EvidenceEngine(store)

    @staticmethod
    def _matches(rule: RuleDefinition, value: float) -> bool:
        if rule.operator == "<":
            return value < rule.threshold
        if rule.operator == "<=":
            return value <= rule.threshold
        if rule.operator == ">":
            return value > rule.threshold
        if rule.operator == ">=":
            return value >= rule.threshold
        if rule.operator == "==":
            return value == rule.threshold
        raise ValueError(f"unsupported operator: {rule.operator}")

    def evaluate(
        self, tenant_id: str, property: Property, actor: str = "system"
    ) -> DecisionResult:
        observations = [
            item
            for item in self.store.observations_for_property(tenant_id, property.id)
            if item.quality_flag == QualityFlag.VALID and item.value is not None
        ]
        metrics: dict[str, list[Observation]] = defaultdict(list)
        for observation in observations:
            metrics[observation.metric].append(observation)

        metric = "soil_moisture"
        rule = self.store.active_rule(tenant_id, metric)
        evidence_ids: list[str] = []
        for observation in metrics.get(metric, []):
            evidence_ids.append(self.evidence.evidence_for_observation(observation).id)

        if rule is None:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há regra ativa versionada para avaliar umidade do solo.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "a ausência de regra não autoriza aplicar um limiar padrão"
                ],
                missing_data=["active_rule:soil_moisture"],
                conflicts=[],
                recommended_action=None,
            )
            self.store.create_decision(decision)
            self._audit(tenant_id, actor, decision, "rule_missing")
            return DecisionResult(decision, None, None)

        current = metrics.get(metric, [])
        if not current:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há evidência suficiente para avaliar a umidade do solo.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=[],
                rule_id=rule.id,
                rule_version=rule.version,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=["nenhum valor observado válido foi recebido"],
                missing_data=["soil_moisture observation"],
                conflicts=[],
                recommended_action=None,
            )
            self.store.create_decision(decision)
            self._audit(tenant_id, actor, decision, "missing_observation")
            return DecisionResult(decision, None, None)

        by_timestamp: dict[str, list[Observation]] = defaultdict(list)
        for item in current:
            by_timestamp[item.observation_timestamp].append(item)
        conflicts: list[dict[str, Any]] = []
        for timestamp, items in by_timestamp.items():
            values = {item.value for item in items}
            if len(items) > 1 and len(values) > 1:
                conflicts.append(
                    {
                        "timestamp": timestamp,
                        "values": sorted(
                            value for value in values if value is not None
                        ),
                        "observation_ids": [item.id for item in items],
                    }
                )
        if conflicts:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Conclusão inconclusiva devido a dados conflitantes de umidade do solo.",
                classification=DataClassification.CONFLICTING,
                status=DecisionStatus.CONFLICTING,
                evidence_ids=evidence_ids,
                rule_id=rule.id,
                rule_version=rule.version,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "não existe regra de precedência configurada entre as fontes conflitantes"
                ],
                missing_data=[],
                conflicts=conflicts,
                recommended_action={
                    "type": "resolve_data_conflict",
                    "responsible_user_id": None,
                },
            )
            self.store.create_decision(decision)
            alert = Alert(
                new_id(),
                tenant_id,
                property.id,
                "DATA_CONFLICT",
                "HIGH",
                "OPEN",
                "Dados conflitantes de umidade do solo",
                decision.id,
            )
            action = Action(
                new_id(),
                tenant_id,
                "resolver conflito de dados",
                "OPEN",
                None,
                None,
                decision.id,
            )
            self.store.create_alert(alert)
            self.store.create_action(action)
            self._audit(tenant_id, actor, decision, "data_conflict", alert, action)
            return DecisionResult(decision, alert, action)

        latest = sorted(current, key=lambda item: item.observation_timestamp)[-1]
        latest_value = latest.value
        if latest_value is None:
            raise ValueError("valid observation must have a numeric value")
        triggered = self._matches(rule, latest_value)
        if triggered:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Foi observada umidade do solo abaixo do limiar configurado; isso sugere possível estresse hídrico e requer inspeção.",
                classification=DataClassification.INFERRED,
                status=DecisionStatus.ACTIONABLE,
                evidence_ids=evidence_ids,
                rule_id=rule.id,
                rule_version=rule.version,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "a observação não determina sozinha a causa agronômica",
                    "satélite ou sensor isolado não confirma doença",
                ],
                missing_data=[],
                conflicts=[],
                recommended_action={
                    "type": "field_inspection",
                    "responsible_user_id": None,
                    "deadline": None,
                },
            )
            self.store.create_decision(decision)
            alert = Alert(
                new_id(),
                tenant_id,
                property.id,
                "RULE_TRIGGERED",
                rule.severity,
                "OPEN",
                "Possível estresse hídrico: inspeção recomendada",
                decision.id,
            )
            action = Action(
                new_id(),
                tenant_id,
                "inspeção de campo",
                "OPEN",
                None,
                None,
                decision.id,
            )
            self.store.create_alert(alert)
            self.store.create_action(action)
            self._audit(tenant_id, actor, decision, "rule_triggered", alert, action)
            return DecisionResult(decision, alert, action)

        decision = Decision(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property.id,
            conclusion="A medição mais recente não acionou o limiar da regra ativa.",
            classification=DataClassification.CALCULATED,
            status=DecisionStatus.NO_TRIGGER,
            evidence_ids=evidence_ids,
            rule_id=rule.id,
            rule_version=rule.version,
            model_id=None,
            model_version=None,
            confidence=None,
            limitations=[],
            missing_data=[],
            conflicts=[],
            recommended_action=None,
        )
        self.store.create_decision(decision)
        self._audit(tenant_id, actor, decision, "rule_not_triggered")
        return DecisionResult(decision, None, None)

    def _audit(
        self,
        tenant_id: str,
        actor: str,
        decision: Decision,
        reason: str,
        alert: Alert | None = None,
        action: Action | None = None,
    ) -> None:
        self.store.audit(
            tenant_id,
            actor,
            "DECISION_CREATED",
            "decision",
            decision.id,
            {
                "reason": reason,
                "input_evidence_ids": decision.evidence_ids,
                "rule_id": decision.rule_id,
                "rule_version": decision.rule_version,
                "model_id": decision.model_id,
                "model_version": decision.model_version,
                "result": decision.conclusion,
                "status": decision.status.value,
                "alert_id": alert.id if alert else None,
                "action_id": action.id if action else None,
            },
            new_id(),
            now_utc(),
        )
