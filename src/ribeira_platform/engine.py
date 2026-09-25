from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
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

    def evaluate_temporal_delta(
        self,
        tenant_id: str,
        property: Property,
        product_id: str,
        mean_delta: float | None,
        evidence_id: str | None,
        provenance_valid: bool,
        actor: str = "system",
        field_id: str | None = None,
        field_boundary_version: int | None = None,
        field_boundary_checksum: str | None = None,
    ) -> DecisionResult:
        metric = "ndvi_temporal_delta_mean"
        evidence_ids = [evidence_id] if evidence_id is not None else []
        if not provenance_valid or mean_delta is None:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="O delta temporal de NDVI não possui proveniência válida para avaliação.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "delta temporal sem proveniência completa não pode acionar recomendação operacional"
                ],
                missing_data=["valid_ndvi_temporal_delta_provenance"],
                conflicts=[],
                recommended_action=None,
            )
            decision = self.store.create_decision(decision)
            self._audit(
                tenant_id, actor, decision, "derived_product_provenance_invalid"
            )
            return DecisionResult(decision, None, None)

        applicable_rules = self.store.active_rules(
            tenant_id, metric, property.id, None, field_id
        )
        if not applicable_rules:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há regra ativa versionada para avaliar a média do delta temporal de NDVI.",
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
                missing_data=[f"active_rule:{metric}"],
                conflicts=[],
                recommended_action=None,
                subject_field_id=field_id,
                subject_field_boundary_version=field_boundary_version,
                subject_field_boundary_checksum=field_boundary_checksum,
            )
            decision = self.store.create_decision(decision)
            self._audit(tenant_id, actor, decision, "rule_missing")
            return DecisionResult(decision, None, None)

        priority = {
            "FIELD": 0,
            "PROPERTY": 1,
            "CUSTOMER": 2,
            "TENANT": 3,
        }
        if field_id is None:
            priority.pop("FIELD")
        supported_rules = [
            rule for rule in applicable_rules if rule.scope_type in priority
        ]
        if not supported_rules:
            raise ValueError(
                "temporal delta evaluation does not support asset or field scope"
            )
        selected_priority = min(priority[rule.scope_type] for rule in supported_rules)
        selected_rules = [
            rule
            for rule in supported_rules
            if priority[rule.scope_type] == selected_priority
        ]
        if len(selected_rules) != 1:
            scope_type = selected_rules[0].scope_type
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Conclusão inconclusiva porque há regras ativas igualmente específicas.",
                classification=DataClassification.CONFLICTING,
                status=DecisionStatus.CONFLICTING,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "a plataforma não escolhe uma regra por ordem de inserção ou versão quando a aplicabilidade é igualmente específica"
                ],
                missing_data=[],
                conflicts=[
                    {
                        "type": "equally_specific_active_rules",
                        "scope_type": scope_type,
                        "rule_versions": [
                            {"rule_id": rule.id, "version": rule.version}
                            for rule in selected_rules
                        ],
                    }
                ],
                recommended_action=None,
                subject_field_id=field_id,
                subject_field_boundary_version=field_boundary_version,
                subject_field_boundary_checksum=field_boundary_checksum,
                selected_rule_scope_type=scope_type,
            )
            decision = self.store.create_decision(decision)
            self._audit(tenant_id, actor, decision, "rule_ambiguity")
            return DecisionResult(decision, None, None)

        rule = selected_rules[0]
        selected_customer_id = (
            rule.scope_customer_id if rule.scope_type == "CUSTOMER" else None
        )
        triggered = self._matches(rule, mean_delta)
        recommendation = (
            {
                "type": "targeted_field_inspection",
                "automated": False,
                "derived_product_id": product_id,
                "metric": metric,
                "responsible_user_id": None,
                "deadline": None,
            }
            if triggered
            else None
        )
        decision = Decision(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property.id,
            conclusion=(
                "A média do delta temporal de NDVI atingiu o limiar configurado; recomenda-se inspeção de campo direcionada, sem inferir diagnóstico."
                if triggered
                else "A média do delta temporal de NDVI não atingiu o limiar configurado."
            ),
            classification=DataClassification.DERIVED,
            status=DecisionStatus.ACTIONABLE
            if triggered
            else DecisionStatus.NO_TRIGGER,
            evidence_ids=evidence_ids,
            rule_id=rule.id,
            rule_version=rule.version,
            model_id=None,
            model_version=None,
            confidence=None,
            limitations=[
                "o delta de NDVI não identifica causa nem confirma diagnóstico agronômico"
            ],
            missing_data=[],
            conflicts=[],
            recommended_action=recommendation,
            subject_field_id=field_id,
            subject_field_boundary_version=field_boundary_version,
            subject_field_boundary_checksum=field_boundary_checksum,
            selected_rule_scope_type=rule.scope_type,
            subject_customer_id=selected_customer_id,
        )
        decision = self.store.create_decision(decision)
        alert = None
        action = None
        if triggered:
            alert = self.store.create_alert(
                Alert(
                    new_id(),
                    tenant_id,
                    property.id,
                    "RULE_TRIGGERED",
                    rule.severity,
                    "OPEN",
                    "Delta temporal de NDVI requer inspeção de campo direcionada",
                    decision.id,
                )
            )
            action = self.store.create_action(
                Action(
                    new_id(),
                    tenant_id,
                    "targeted field inspection recommendation",
                    "OPEN",
                    None,
                    None,
                    decision.id,
                )
            )
        self._audit(
            tenant_id,
            actor,
            decision,
            "rule_triggered" if triggered else "rule_not_triggered",
            alert,
            action,
        )
        return DecisionResult(decision, alert, action)

    def evaluate(
        self,
        tenant_id: str,
        property: Property,
        actor: str = "system",
        *,
        asset_id: str | None = None,
        asset_evidence_id: str | None = None,
        field_id: str | None = None,
        field_evidence_id: str | None = None,
        field_boundary_version: int | None = None,
        field_boundary_checksum: str | None = None,
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
        evidence_ids: list[str] = []
        for observation in metrics.get(metric, []):
            evidence_ids.append(self.evidence.evidence_for_observation(observation).id)

        if asset_id is not None and asset_evidence_id is None:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há evidência de registro disponível para usar o ativo como contexto da regra.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "um ativo sem proveniência registrada não pode restringir a aplicabilidade de uma regra"
                ],
                missing_data=["asset_registration_evidence"],
                conflicts=[],
                recommended_action=None,
            )
            decision = self._persist_decision(decision, asset_id)
            self._audit(tenant_id, actor, decision, "asset_context_evidence_missing")
            return DecisionResult(decision, None, None)
        if asset_evidence_id is not None:
            evidence_ids.append(asset_evidence_id)

        if field_id is not None and field_evidence_id is None:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há evidência de registro disponível para usar o talhão como contexto da regra.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "um talhão sem proveniência registrada não pode restringir a aplicabilidade de uma regra"
                ],
                missing_data=["field_registration_evidence"],
                conflicts=[],
                recommended_action=None,
            )
            decision = self._persist_decision(
                decision,
                asset_id,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
            self._audit(tenant_id, actor, decision, "field_context_evidence_missing")
            return DecisionResult(decision, None, None)
        if field_evidence_id is not None:
            evidence_ids.append(field_evidence_id)

        applicable_rules = self.store.active_rules(
            tenant_id, metric, property.id, asset_id, field_id
        )
        if not applicable_rules:
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
            decision = self._persist_decision(
                decision,
                asset_id,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
            self._audit(tenant_id, actor, decision, "rule_missing")
            return DecisionResult(decision, None, None)

        priority = {"ASSET": 0, "FIELD": 1, "PROPERTY": 2, "CUSTOMER": 3, "TENANT": 4}
        selected_priority = min(priority[rule.scope_type] for rule in applicable_rules)
        selected_rules = [
            rule
            for rule in applicable_rules
            if priority[rule.scope_type] == selected_priority
        ]
        if len(selected_rules) != 1:
            scope_type = selected_rules[0].scope_type
            customer_ids = {
                rule.scope_customer_id
                for rule in selected_rules
                if rule.scope_customer_id is not None
            }
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Conclusão inconclusiva porque há regras ativas igualmente específicas.",
                classification=DataClassification.CONFLICTING,
                status=DecisionStatus.CONFLICTING,
                evidence_ids=evidence_ids,
                rule_id=None,
                rule_version=None,
                model_id=None,
                model_version=None,
                confidence=None,
                limitations=[
                    "a plataforma não escolhe uma regra por ordem de inserção ou versão quando a aplicabilidade é igualmente específica"
                ],
                missing_data=[],
                conflicts=[
                    {
                        "type": "equally_specific_active_rules",
                        "scope_type": scope_type,
                        "rules": [
                            {"id": rule.id, "version": rule.version}
                            for rule in selected_rules
                        ],
                    }
                ],
                recommended_action={
                    "type": "resolve_rule_conflict",
                    "responsible_user_id": None,
                },
                selected_rule_scope_type=scope_type,
                subject_customer_id=(
                    next(iter(customer_ids))
                    if scope_type == "CUSTOMER" and len(customer_ids) == 1
                    else None
                ),
            )
            decision = self._persist_decision(
                decision,
                asset_id,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
            self._audit(tenant_id, actor, decision, "rule_scope_conflict")
            return DecisionResult(decision, None, None)
        rule = selected_rules[0]

        current = metrics.get(metric, [])
        if not current:
            decision = Decision(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                conclusion="Não há evidência suficiente para avaliar a umidade do solo.",
                classification=DataClassification.UNKNOWN,
                status=DecisionStatus.INCONCLUSIVE,
                evidence_ids=evidence_ids,
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
            decision = self._persist_decision(
                decision,
                asset_id,
                rule,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
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
            decision = self._persist_decision(
                decision,
                asset_id,
                rule,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
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
            decision = self._persist_decision(
                decision,
                asset_id,
                rule,
                field_id=field_id,
                field_boundary_version=field_boundary_version,
                field_boundary_checksum=field_boundary_checksum,
            )
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
        decision = self._persist_decision(
            decision,
            asset_id,
            rule,
            field_id=field_id,
            field_boundary_version=field_boundary_version,
            field_boundary_checksum=field_boundary_checksum,
        )
        self._audit(tenant_id, actor, decision, "rule_not_triggered")
        return DecisionResult(decision, None, None)

    def _persist_decision(
        self,
        decision: Decision,
        asset_id: str | None,
        rule: RuleDefinition | None = None,
        *,
        field_id: str | None = None,
        field_boundary_version: int | None = None,
        field_boundary_checksum: str | None = None,
    ) -> Decision:
        """Persist immutable applicability context without inferring customer facts."""
        if rule is not None:
            decision = replace(
                decision,
                selected_rule_scope_type=rule.scope_type,
                subject_customer_id=(
                    rule.scope_customer_id if rule.scope_type == "CUSTOMER" else None
                ),
            )
        if asset_id is not None:
            decision = replace(
                decision,
                subject_asset_id=asset_id,
                limitations=[
                    *decision.limitations,
                    "o ativo é contexto factual de aplicabilidade; não é uma medição",
                ],
            )
        if field_id is not None:
            decision = replace(
                decision,
                subject_field_id=field_id,
                subject_field_boundary_version=field_boundary_version,
                subject_field_boundary_checksum=field_boundary_checksum,
                limitations=[
                    *decision.limitations,
                    "o talhão é contexto operacional não legal; não é evidência de cultura, solo ou diagnóstico",
                ],
            )
        self.store.create_decision(decision)
        return decision

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
                "subject_asset_id": decision.subject_asset_id,
                "subject_field_id": decision.subject_field_id,
                "selected_rule_scope_type": decision.selected_rule_scope_type,
                "subject_customer_id": decision.subject_customer_id,
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
