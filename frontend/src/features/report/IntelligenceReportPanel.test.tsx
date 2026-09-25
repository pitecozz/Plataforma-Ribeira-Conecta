import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IntelligenceReportPanel } from "./IntelligenceReportPanel";

const property = { id: "property", tenant_id: "tenant", name: "Sítio Piloto", geometry_geojson: null, geometry_crs: null, boundary_source: "MANUAL_CONFIRMED", area_hectares: "4", classification: "MANUAL_CONFIRMED", created_at: "2026-09-22T00:00:00Z", data_status: "UNKNOWN" } as const;

describe("IntelligenceReportPanel", () => {
  it("renders available records and states unavailable decision data explicitly", () => {
    render(<IntelligenceReportPanel property={property} assets={[]} scenes={[]} provenance={null} decisions={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir relatório" }));
    expect(screen.getByRole("heading", { name: "Relatório de Inteligência Farm360" })).toBeInTheDocument();
    expect(screen.getByText(/ainda não há ativos confirmados/i)).toBeInTheDocument();
    expect(screen.getByText(/ausência de registro não confirma ausência de risco/i)).toBeInTheDocument();
    expect(screen.getByText("Detalhes técnicos, proveniência e auditoria")).toBeInTheDocument();
  });

  it("includes completed action result provenance in the report", () => {
    render(<IntelligenceReportPanel property={property} assets={[]} scenes={[]} provenance={null} decisions={[{
      id: "decision-completed", property_id: "property", conclusion: "Inspect the field.",
      classification: "INFERRED", status: "ACTIONABLE", evidence_ids: ["decision-evidence"],
      rule_id: "rule-1", rule_version: 4, limitations: [], missing_data: [], conflicts: [],
      recommended_action: null, created_at: "2026-09-24T00:00:00Z", action: {
        id: "action-1", status: "COMPLETED", completed_at: "2026-09-24T15:30:00Z",
        completed_by: "field-technician", outcome_detail: "Inspection completed without visible damage.",
        outcome_classification: "MANUAL_CONFIRMED", outcome_evidence_ids: ["photo-1", "inspection-1"],
      },
    }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir relatório" }));

    expect(screen.getAllByRole("heading", { name: "Riscos, decisões e resultados", level: 2 }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Inspection completed without visible damage.").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle("Estado técnico: MANUAL_CONFIRMED").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/24 de set\. de 2026/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("field-technician").length).toBeGreaterThan(0);
    expect(screen.getAllByText("photo-1, inspection-1").length).toBeGreaterThan(0);
  });

  it("includes field-scoped decision context without turning registration into diagnosis", () => {
    render(<IntelligenceReportPanel property={property} assets={[]} scenes={[]} provenance={null} fields={[{
      id: "field-1", tenant_id: "tenant", property_id: "property", name: "Talhão Norte",
      status: "ACTIVE", geometry_geojson: { type: "Polygon", coordinates: [] }, geometry_crs: "EPSG:4326",
      boundary_version: 3, boundary_checksum: "current-checksum", source_reference: "survey.geojson",
      observed_at: "2026-09-24T00:00:00Z", classification: "MANUAL_CONFIRMED", created_at: "2026-09-24T00:00:00Z",
    }]} decisions={[{
      id: "decision-1", property_id: "property", subject_field_id: "field-1",
      subject_field_boundary_version: 2, subject_field_boundary_checksum: "evaluated-checksum",
      selected_rule_scope_type: "FIELD", conclusion: "Inspect the field.", classification: "INFERRED",
      status: "ACTIONABLE", evidence_ids: ["evidence-1"], rule_id: "rule-1", rule_version: 4,
      limitations: [], missing_data: [], conflicts: [], recommended_action: null,
      created_at: "2026-09-24T00:00:00Z", action: null,
    }]} />);

    fireEvent.click(screen.getByRole("button", { name: "Abrir relatório" }));
    expect(screen.getByText(/escopo: talhão · talhão norte/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Contexto técnico do talhão"));
    expect(screen.getByText("evaluated-checksum")).toBeInTheDocument();
    expect(screen.getByText(/não comprova cultivo, solo, doença ou diagnóstico agronômico/i)).toBeInTheDocument();
  });
});
