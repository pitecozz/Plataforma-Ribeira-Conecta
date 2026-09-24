import { useState, type FormEvent } from "react";

import type { Farm360Api } from "../../api/client";
import type { PropertyDecision } from "../../types/farm360";

const classifications = [
  "MANUAL_CONFIRMED",
  "OBSERVED",
  "OFFICIAL_SOURCE",
  "CALCULATED",
  "DERIVED",
  "INFERRED",
  "PREDICTED",
  "UNKNOWN",
  "CONFLICTING",
];

function evidenceIds(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
}

export function ActionOutcomePanel({
  api,
  tenantId,
  action,
  onCompleted,
}: {
  api: Farm360Api;
  tenantId: string;
  action: NonNullable<PropertyDecision["action"]>;
  onCompleted: () => Promise<void> | void;
}) {
  const [detail, setDetail] = useState("");
  const [classification, setClassification] = useState("MANUAL_CONFIRMED");
  const [completedAt, setCompletedAt] = useState("");
  const [evidence, setEvidence] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    const timestamp = new Date(completedAt);
    if (!detail.trim() || Number.isNaN(timestamp.getTime())) {
      setMessage("DADO_INSUFICIENTE — descreva o resultado e informe quando ele foi registrado.");
      return;
    }
    setSaving(true);
    try {
      await api.completeAction(tenantId, action.id, {
        outcome_detail: detail.trim(),
        outcome_classification: classification,
        evidence_ids: evidenceIds(evidence),
        completed_at: timestamp.toISOString(),
      });
      await onCompleted();
      setMessage("Resultado registrado. A decisão e a recomendação originais foram preservadas.");
    } catch {
      setMessage("Não foi possível registrar o resultado agora. Confirme a permissão, os identificadores de evidência e tente novamente.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="action-outcome-panel">
      <summary>Registrar resultado da ação</summary>
      <p>
        Registre somente o resultado que foi observado, calculado ou confirmado.
        A recomendação original não será alterada.
      </p>
      <form onSubmit={submit}>
        <label>
          Resultado registrado
          <textarea value={detail} onChange={(event) => setDetail(event.target.value)} maxLength={4000} required />
        </label>
        <label>
          Classificação do resultado
          <select value={classification} onChange={(event) => setClassification(event.target.value)}>
            {classifications.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          Registrado em
          <input aria-label="Resultado registrado em" type="datetime-local" value={completedAt} onChange={(event) => setCompletedAt(event.target.value)} required />
        </label>
        <label>
          Identificadores de evidência de resultado (opcional)
          <textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="Um identificador por linha ou separado por vírgula" />
        </label>
        <p>Não copie evidências da decisão por padrão: informe apenas as que sustentam este resultado.</p>
        <button type="submit" disabled={saving}>{saving ? "Registrando…" : "Registrar resultado"}</button>
      </form>
      {message && <p role="alert">{message}</p>}
    </details>
  );
}
