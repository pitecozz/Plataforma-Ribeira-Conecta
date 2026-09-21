import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IntelligenceReportPanel } from "./IntelligenceReportPanel";

const property = { id: "property", tenant_id: "tenant", name: "Sítio Piloto", geometry_geojson: null, geometry_crs: null, boundary_source: "MANUAL_CONFIRMED", area_hectares: "4", classification: "MANUAL_CONFIRMED", created_at: "2026-09-22T00:00:00Z", data_status: "UNKNOWN" } as const;

describe("IntelligenceReportPanel", () => {
  it("renders available records and states unavailable decision data explicitly", () => {
    render(<IntelligenceReportPanel property={property} assets={[]} scenes={[]} provenance={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir relatório" }));
    expect(screen.getByRole("heading", { name: "Farm360 Intelligence Report" })).toBeInTheDocument();
    expect(screen.getByText(/nenhum ativo confirmado/i)).toBeInTheDocument();
    expect(screen.getByText(/ainda não apresenta um resumo customer-facing/i)).toBeInTheDocument();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
  });
});
