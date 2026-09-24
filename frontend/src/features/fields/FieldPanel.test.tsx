import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { FieldPanel } from "./FieldPanel";
import type { FieldContext } from "../../types/farm360";

const field: FieldContext = {
  id: "field-1",
  tenant_id: "tenant",
  property_id: "property",
  name: "Talhão sintético",
  status: "ACTIVE",
  geometry_geojson: { type: "Polygon", coordinates: [[[-47, -24], [-46.9, -24], [-46.9, -24.1], [-47, -24]]] },
  geometry_crs: "EPSG:4326",
  boundary_version: 1,
  boundary_checksum: "a".repeat(64),
  source_reference: "synthetic test data field walk",
  observed_at: "2026-09-24T12:00:00+00:00",
  classification: "MANUAL_CONFIRMED",
  created_at: "2026-09-24T12:00:00+00:00",
  evidence_id: "evidence-1",
};

describe("FieldPanel", () => {
  it("keeps an empty field inventory explicitly insufficient", () => {
    render(<FieldPanel fields={[]} />);
    expect(screen.getByText(/DADO_INSUFICIENTE — não há talhão/i)).toBeInTheDocument();
  });

  it("shows geometry, source, boundary reference and evidence without agronomic interpretation", () => {
    render(<FieldPanel fields={[field]} />);
    expect(screen.getByRole("heading", { name: "Talhão sintético" })).toBeInTheDocument();
    expect(screen.getByText("synthetic test data field walk")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Detalhes técnicos e proveniência"));
    expect(screen.getByText("evidence-1")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText(/recomendação agronômica/i)).not.toBeInTheDocument();
  });

  it("posts only an explicit source-backed WGS84 field registration", async () => {
    const registerField = vi.fn().mockResolvedValue(field);
    const onCreated = vi.fn();
    render(<FieldPanel fields={[]} api={{ registerField } as never} tenantId="tenant" propertyId="property" canManageFields onCreated={onCreated} />);
    fireEvent.click(screen.getByText("Registrar talhão", { selector: "summary" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Nome" }), { target: { value: "Talhão novo" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Fonte ou referência de confirmação" }), { target: { value: "synthetic_test_data walk" } });
    fireEvent.change(screen.getByLabelText("Talhão observado em"), { target: { value: "2026-09-24T12:00" } });
    fireEvent.change(screen.getByRole("textbox", { name: "GeoJSON técnico (WGS84)" }), { target: { value: JSON.stringify(field.geometry_geojson) } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar talhão" }));
    expect(registerField).toHaveBeenCalledWith("tenant", "property", expect.objectContaining({
      name: "Talhão novo",
      geometry_crs: "EPSG:4326",
      source_reference: "synthetic_test_data walk",
      classification: "MANUAL_CONFIRMED",
    }));
    await screen.findByText(/Talhão registrado com fonte e evidência próprias/i);
    expect(onCreated).toHaveBeenCalledWith(field);
  });
});
