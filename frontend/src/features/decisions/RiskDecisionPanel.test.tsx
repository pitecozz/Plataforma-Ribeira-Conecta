import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RiskDecisionPanel } from "./RiskDecisionPanel";

describe("RiskDecisionPanel", () => {
  it("keeps an empty property decision history explicitly unknown", () => {
    render(<RiskDecisionPanel decisions={[]} />);
    expect(screen.getByText(/não há decisão persistida aplicável/i)).toBeInTheDocument();
    expect(screen.getByText(/ausência de registro não confirma ausência de risco/i)).toBeInTheDocument();
  });

  it("does not expose outcome capture without action:write", () => {
    render(<RiskDecisionPanel decisions={[{
      id: "decision-1", property_id: "property-1", conclusion: "Inspect the pump.",
      classification: "INFERRED", status: "ACTIONABLE", evidence_ids: [], rule_id: "rule-1",
      rule_version: 1, limitations: [], missing_data: [], conflicts: [], recommended_action: null,
      created_at: "2026-09-24T00:00:00Z",
      action: { id: "action-1", status: "OPEN", completed_at: null, completed_by: null, outcome_detail: null, outcome_classification: null, outcome_evidence_ids: [] },
    }]} />);
    expect(screen.queryByText("Registrar resultado da ação")).not.toBeInTheDocument();
  });

  it("records an explicit outcome only for an authorized open action", async () => {
    const completeAction = vi.fn().mockResolvedValue({ id: "action-1", status: "COMPLETED" });
    const onActionCompleted = vi.fn().mockResolvedValue(undefined);
    render(<RiskDecisionPanel
      api={{ completeAction } as never}
      tenantId="tenant-1"
      canCompleteActions
      onActionCompleted={onActionCompleted}
      decisions={[{
        id: "decision-1", property_id: "property-1", conclusion: "Inspect the pump.",
        classification: "INFERRED", status: "ACTIONABLE", evidence_ids: ["decision-evidence"],
        rule_id: "rule-1", rule_version: 1, limitations: [], missing_data: [], conflicts: [],
        recommended_action: { type: "INSPECT" }, created_at: "2026-09-24T00:00:00Z",
        action: { id: "action-1", status: "OPEN", completed_at: null, completed_by: null, outcome_detail: null, outcome_classification: null, outcome_evidence_ids: [] },
      }]}
    />);
    fireEvent.click(screen.getByText("Registrar resultado da ação"));
    fireEvent.change(screen.getByLabelText("Resultado registrado"), { target: { value: "Pump inspection was completed." } });
    fireEvent.change(screen.getByLabelText("Resultado registrado em"), { target: { value: "2026-09-24T15:30" } });
    fireEvent.change(screen.getByLabelText(/Identificadores de evidência/i), { target: { value: "outcome-evidence, outcome-evidence\nsecond-evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar resultado" }));
    await waitFor(() => expect(completeAction).toHaveBeenCalledWith("tenant-1", "action-1", expect.objectContaining({
      outcome_detail: "Pump inspection was completed.", outcome_classification: "MANUAL_CONFIRMED", evidence_ids: ["outcome-evidence", "second-evidence"],
    })));
    expect(onActionCompleted).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("decisão e a recomendação originais foram preservadas");
  });
});
