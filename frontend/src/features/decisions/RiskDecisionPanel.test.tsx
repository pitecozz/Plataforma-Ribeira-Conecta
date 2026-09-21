import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDecisionPanel } from "./RiskDecisionPanel";

describe("RiskDecisionPanel", () => {
  it("keeps an empty property decision history explicitly unknown", () => {
    render(<RiskDecisionPanel decisions={[]} />);
    expect(screen.getByText(/não há decisão persistida aplicável/i)).toBeInTheDocument();
    expect(screen.getByText(/ausência de decisão não confirma ausência de risco/i)).toBeInTheDocument();
  });
});
