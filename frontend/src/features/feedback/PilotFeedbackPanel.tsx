import { useState, type FormEvent } from "react";

import type { Farm360Api } from "../../api/client";
import type { PilotFeedbackType } from "../../types/farm360";
import "./PilotFeedbackPanel.css";

const choices: Array<{ value: PilotFeedbackType; label: string }> = [
  { value: "BUG", label: "Erro" },
  { value: "CONFUSING", label: "Confuso" },
  { value: "INCORRECT_DATA", label: "Dado incorreto" },
  { value: "MISSING_FEATURE", label: "Recurso ausente" },
  { value: "SUGGESTION", label: "Sugestão" },
  { value: "USEFUL", label: "Útil" },
];

export function PilotFeedbackPanel({
  api,
  tenantId,
  propertyId,
}: {
  api: Farm360Api;
  tenantId: string;
  propertyId: string;
}) {
  const [feedbackType, setFeedbackType] = useState<PilotFeedbackType>("SUGGESTION");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim()) return;
    setState("sending");
    try {
      await api.submitPilotFeedback(tenantId, {
        feedback_type: feedbackType,
        page: "farm360",
        feature_id: "F-FEEDBACK-001",
        property_id: propertyId,
        message: message.trim(),
      });
      setMessage("");
      setState("sent");
    } catch {
      setState("error");
    }
  }

  return <section className="pilot-feedback"><h2>Feedback do piloto</h2><p>Seu comentário fica associado a esta propriedade, ao usuário autenticado e à tela Farm360.</p><form onSubmit={submit}><label>Tipo<select aria-label="Tipo de feedback" value={feedbackType} onChange={(event) => setFeedbackType(event.target.value as PilotFeedbackType)}>{choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></label><label>Mensagem<textarea aria-label="Mensagem de feedback" value={message} maxLength={4000} required onChange={(event) => { setMessage(event.target.value); setState("idle"); }} /></label><button type="submit" disabled={state === "sending"}>{state === "sending" ? "Enviando…" : "Enviar feedback"}</button></form>{state === "sent" && <p role="status">Recebido. Obrigado por ajudar a melhorar o piloto.</p>}{state === "error" && <p role="alert">Não foi possível enviar agora. Tente novamente; nenhum comentário foi presumido como recebido.</p>}</section>;
}
