import type { Farm360Api } from "../../api/client";
import { Status } from "../../components/Status";
import { customerDateLabel } from "../../presentation";
import type { FieldContext, PropertyDecision } from "../../types/farm360";
import { ActionOutcomePanel } from "./ActionOutcomePanel";
import { decisionFieldLabel, decisionScopeLabel } from "./decisionPresentation";

export function RiskDecisionPanel({ decisions, fields = [], api, tenantId, canCompleteActions = false, onActionCompleted }: { decisions: PropertyDecision[]; fields?: FieldContext[]; api?: Farm360Api; tenantId?: string; canCompleteActions?: boolean; onActionCompleted?: () => Promise<void> | void; }) {
  return <section className="risk-decision-panel">
    <h2>Riscos e decisões</h2>
    {decisions.length === 0 ? <p>Ainda não há decisão persistida aplicável a esta propriedade. A ausência de registro não confirma ausência de risco ou oportunidade.</p> : <ul>{decisions.map((decision) => {
      const fieldLabel = decisionFieldLabel(decision, fields);
      return <li key={decision.id}>
        <p><Status value={decision.status} /> <Status value={decision.classification} /></p>
        <p>{decision.conclusion}</p>
        <p>Escopo aplicado: {decisionScopeLabel(decision)}{fieldLabel ? ` · ${fieldLabel}` : ""}</p>
        {decision.recommended_action && <p>Ação recomendada: {String(decision.recommended_action.type ?? "Ainda não informado")}</p>}
        {decision.action && <div>
          <p>Ação: <Status value={decision.action.status} /></p>
          {decision.action.status === "COMPLETED" && <dl>
            <dt>Resultado registrado</dt><dd>{decision.action.outcome_detail ?? "Resultado não registrado"}</dd>
            <dt>Classificação do resultado</dt><dd>{decision.action.outcome_classification ? <Status value={decision.action.outcome_classification} /> : "Não registrada"}</dd>
            <dt>Concluída em</dt><dd>{decision.action.completed_at ? customerDateLabel(decision.action.completed_at) : "Não registrado"}</dd>
            <dt>Registrada por</dt><dd>{decision.action.completed_by ?? "Não registrado"}</dd>
            <dt>Evidências do resultado</dt><dd>{decision.action.outcome_evidence_ids.length > 0 ? decision.action.outcome_evidence_ids.join(", ") : "Nenhuma registrada"}</dd>
          </dl>}
        </div>}
        {decision.action?.status === "OPEN" && canCompleteActions && api && tenantId && onActionCompleted && <ActionOutcomePanel api={api} tenantId={tenantId} action={decision.action} onCompleted={onActionCompleted} />}
        <details><summary>Detalhes técnicos e evidências</summary><dl>
          <dt>Regra</dt><dd>{decision.rule_id && decision.rule_version !== null ? `${decision.rule_id} · versão ${decision.rule_version}` : "Não registrada"}</dd>
          <dt>Evidências vinculadas</dt><dd>{decision.evidence_ids.length > 0 ? decision.evidence_ids.join(", ") : "Nenhuma registrada"}</dd>
          {decision.subject_field_id && <>
            <dt>Identificador do talhão</dt><dd>{decision.subject_field_id}</dd>
            <dt>Versão do limite avaliado</dt><dd>{decision.subject_field_boundary_version ?? "Não registrada"}</dd>
            <dt>Checksum do limite avaliado</dt><dd>{decision.subject_field_boundary_checksum ?? "Não registrado"}</dd>
            <dt>Limitação</dt><dd>A decisão preserva o limite do talhão usado na avaliação; uma correção posterior não altera esta evidência histórica.</dd>
          </>}
          <dt>Limitações</dt><dd>{decision.limitations.length > 0 ? decision.limitations.join("; ") : "Nenhuma registrada"}</dd>
          <dt>Dados ausentes</dt><dd>{decision.missing_data.length > 0 ? decision.missing_data.join("; ") : "Nenhum registrado"}</dd>
        </dl>{decision.subject_field_id && <p>O cadastro do talhão define contexto de aplicabilidade; não comprova cultivo, solo, doença ou diagnóstico agronômico.</p>}</details>
      </li>;
    })}</ul>}
  </section>;
}
