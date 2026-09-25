import type { FieldContext, PropertyDecision } from "../../types/farm360";

const scopeLabels: Record<string, string> = {
  FIELD: "Talhão",
  PROPERTY: "Propriedade",
  ASSET: "Ativo",
  CUSTOMER: "Cliente",
  TENANT: "Organização",
};

export function decisionScopeLabel(decision: PropertyDecision): string {
  if (!decision.selected_rule_scope_type) return "Escopo histórico não registrado";
  return scopeLabels[decision.selected_rule_scope_type] ?? decision.selected_rule_scope_type;
}

export function decisionFieldLabel(decision: PropertyDecision, fields: FieldContext[]): string | null {
  if (!decision.subject_field_id) return null;
  return fields.find((field) => field.id === decision.subject_field_id)?.name ?? "Talhão referenciado não disponível no inventário atual";
}
