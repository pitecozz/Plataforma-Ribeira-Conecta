import type { PropertyDecision } from "../../types/farm360";
import { Status } from "../../components/Status";

export function RiskDecisionPanel({ decisions }: { decisions: PropertyDecision[] }) {
  return <section className="risk-decision-panel"><h2>Riscos e decisões</h2>{decisions.length === 0 ? <p>UNKNOWN — não há decisão persistida aplicável a esta propriedade. A ausência de decisão não confirma ausência de risco ou oportunidade.</p> : <ul>{decisions.map((decision) => <li key={decision.id}><p><Status value={decision.status} /> <Status value={decision.classification} /></p><p>{decision.conclusion}</p>{decision.recommended_action && <p>Ação recomendada: {String(decision.recommended_action.type ?? "UNKNOWN")}</p>}{decision.action && <p>Ação: <Status value={decision.action.status} />{decision.action.outcome_detail ? ` — resultado: ${decision.action.outcome_detail}` : ""}</p>}<p>Evidências vinculadas: {decision.evidence_ids.length}. Dados ausentes: {decision.missing_data.join(", ") || "nenhum registrado"}.</p></li>)}</ul>}<p>Oportunidades comerciais não são inferidas por esta tela; exigem evidência → necessidade → serviço aplicável.</p></section>;
}
