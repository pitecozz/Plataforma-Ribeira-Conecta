import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PilotFeedbackPanel } from "./PilotFeedbackPanel";

describe("PilotFeedbackPanel", () => {
  it("submits explicit feedback with the active property context", async () => {
    const submitPilotFeedback = vi.fn().mockResolvedValue({ id: "feedback" });
    render(<PilotFeedbackPanel api={{ submitPilotFeedback } as never} tenantId="tenant" propertyId="property" />);
    fireEvent.change(screen.getByLabelText("Tipo de feedback"), { target: { value: "CONFUSING" } });
    fireEvent.change(screen.getByLabelText("Mensagem de feedback"), { target: { value: "The report limitation needs more context." } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar feedback" }));
    await waitFor(() => expect(submitPilotFeedback).toHaveBeenCalledWith("tenant", {
      feedback_type: "CONFUSING", page: "farm360", feature_id: "F-FEEDBACK-001",
      property_id: "property", message: "The report limitation needs more context.",
    }));
    expect(screen.getByRole("status")).toHaveTextContent("Recebido");
  });
});
