import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { FieldPanel } from "./FieldPanel";
import type { FieldContext } from "../../types/farm360";

vi.mock("../map/MapCanvas", () => ({
  MapCanvas: ({ aoi, onMapClick }: { aoi: { type: string }; onMapClick?: (point: [number, number]) => void }) => (
    <div data-testid="field-draft-map" data-geometry={aoi.type}>
      <button type="button" onClick={() => onMapClick?.([-47.2, -24.1])}>Adicionar primeiro ponto</button>
      <button type="button" onClick={() => onMapClick?.([-47.1, -24.1])}>Adicionar segundo ponto</button>
      <button type="button" onClick={() => onMapClick?.([-47.1, -24.2])}>Adicionar terceiro ponto</button>
    </div>
  ),
}));

const propertyGeometry = { type: "Polygon" as const, coordinates: [[[-47.3, -24], [-47, -24], [-47, -24.3], [-47.3, -24]]] };

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
    expect(screen.getByText(/não há talhão confirmado/i)).toBeInTheDocument();
  });

  it("shows geometry, source, boundary reference and evidence without agronomic interpretation", () => {
    render(<FieldPanel fields={[field]} />);
    expect(screen.getByRole("heading", { name: "Talhão sintético" })).toBeInTheDocument();
    expect(screen.getByText(/synthetic test data field walk/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Detalhes técnicos e proveniência"));
    expect(screen.getByText("evidence-1")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText(/recomendação agronômica/i)).not.toBeInTheDocument();
  });

  it("builds a provisional polygon from map clicks before registration", () => {
    render(<FieldPanel fields={[]} api={{ registerField: vi.fn() } as never} tenantId="tenant" propertyId="property" propertyGeometry={propertyGeometry} apiBaseUrl="/api" token="test" canManageFields onCreated={vi.fn()} />);
    fireEvent.click(screen.getByText("Registrar talhão", { selector: "summary" }));
    expect(screen.getByTestId("field-draft-map")).toHaveAttribute("data-geometry", "Polygon");
    fireEvent.click(screen.getByText("Adicionar primeiro ponto"));
    fireEvent.click(screen.getByText("Adicionar segundo ponto"));
    fireEvent.click(screen.getByText("Adicionar terceiro ponto"));
    expect(screen.getByText("3 vértice(s) selecionado(s).")).toBeInTheDocument();
    expect(screen.getByLabelText("GeoJSON técnico (WGS84)")).toHaveValue(JSON.stringify({ type: "Polygon", coordinates: [[[-47.2, -24.1], [-47.1, -24.1], [-47.1, -24.2], [-47.2, -24.1]]] }));
    fireEvent.click(screen.getByText("Desfazer último ponto"));
    expect(screen.getByText("2 vértice(s) selecionado(s).")).toBeInTheDocument();
    expect(screen.getByLabelText("GeoJSON técnico (WGS84)")).toHaveValue("");
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
