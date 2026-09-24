import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Farm360Api } from "../../api/client";
import type { PropertyRecord } from "../../types/farm360";
import { BoundaryEditorPanel } from "./BoundaryEditorPanel";

afterEach(cleanup);

vi.mock("../map/MapCanvas", () => ({
  MapCanvas: ({ aoi, onMapClick }: { aoi: { type: string; coordinates: number[][][] }; onMapClick?: (point: [number, number]) => void }) => (
    <div data-testid="boundary-draft-map" data-vertices={aoi.coordinates[0].length - 1}>
      <button type="button" onClick={() => onMapClick?.([-47.4, -24.3])}>Adicionar ponto no mapa</button>
    </div>
  ),
}));

const property: PropertyRecord = {
  id: "property",
  tenant_id: "tenant",
  name: "Sítio de teste",
  geometry_geojson: {
    type: "Polygon",
    coordinates: [[[-47.2, -24.1], [-47.1, -24.1], [-47.1, -24.2], [-47.2, -24.1]]],
  },
  geometry_crs: "EPSG:4326",
  boundary_source: "CUSTOMER_DRAWN_IN_RIBEIRA_MAPS",
  boundary_checksum: "a".repeat(64),
  area_hectares: "10",
  classification: "MANUAL_CONFIRMED",
  created_at: "2026-09-24T00:00:00Z",
  updated_at: null,
  data_status: "READY",
};

function apiFor() {
  return { updateBoundary: vi.fn().mockResolvedValue(property) } as unknown as Farm360Api;
}

describe("BoundaryEditorPanel", () => {
  it("previews an explicit map-click draft and persists only when saved", async () => {
    const api = apiFor();
    const changed = vi.fn();
    render(<BoundaryEditorPanel api={api} apiBaseUrl="/api" tenantId="tenant" property={property} token="test" onChanged={changed} />);

    fireEvent.click(screen.getByRole("button", { name: "Editar limite no mapa" }));
    expect(screen.getByTestId("boundary-draft-map")).toHaveAttribute("data-vertices", "3");
    fireEvent.click(screen.getByRole("button", { name: "Adicionar ponto no mapa" }));
    expect(screen.getByTestId("boundary-draft-map")).toHaveAttribute("data-vertices", "4");
    expect(api.updateBoundary).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Salvar nova versão" }));
    expect(api.updateBoundary).toHaveBeenCalledWith("tenant", "property", expect.objectContaining({
      geometry_geojson: {
        type: "Polygon",
        coordinates: [[[-47.2, -24.1], [-47.1, -24.1], [-47.1, -24.2], [-47.4, -24.3], [-47.2, -24.1]]],
      },
      expected_checksum: property.boundary_checksum,
    }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  });

  it("keeps an invalid draft local and explains why it was not submitted", async () => {
    const api = apiFor();
    render(<BoundaryEditorPanel api={api} apiBaseUrl="/api" tenantId="tenant" property={property} token="test" onChanged={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Editar limite no mapa" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Longitude 1" }), { target: { value: "181" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar nova versão" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("longitude entre");
    expect(api.updateBoundary).not.toHaveBeenCalled();
  });
});
