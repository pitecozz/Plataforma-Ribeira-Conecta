import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Farm360Api } from "../api/client";
import { Farm360Page } from "./Farm360Page";

vi.mock("../features/map/MapCanvas", () => ({
  MapCanvas: ({ aoi }: { aoi: unknown }) => <div data-testid="property-map">{aoi ? "boundary-ready" : "boundary-missing"}</div>,
}));

vi.mock("../features/operations/SceneOperationsPanel", () => ({
  SceneOperationsPanel: () => null,
}));

vi.mock("../features/property/BoundaryImportPanel", () => ({
  BoundaryImportPanel: () => null,
}));

afterEach(cleanup);

const property = {
  id: "property-hamilton",
  tenant_id: "tenant-hamilton",
  name: "Sítio Hamilton",
  geometry_geojson: { type: "Polygon", coordinates: [[[-47, -24], [-46.9, -24], [-46.9, -24.1], [-47, -24]]] },
  geometry_crs: "EPSG:4326",
  boundary_source: "USER_PROVIDED_GOOGLE_EARTH_KML",
  boundary_checksum: "a".repeat(64),
  area_hectares: "63.86741722620799",
  classification: "MANUAL_CONFIRMED",
  created_at: "2026-09-22T00:00:00Z",
  updated_at: null,
  data_status: "DADO_INSUFICIENTE",
};

const asset = {
  id: "asset-house",
  tenant_id: "tenant-hamilton",
  property_id: "property-hamilton",
  asset_type: "BUILDING",
  name: "Casa hamilton",
  status: "ACTIVE",
  classification: "MANUAL_CONFIRMED",
  geometry_geojson: { type: "Point", coordinates: [-46.95, -24.05] },
  geometry_crs: "EPSG:4326",
  source_reference: "USER_PROVIDED_GOOGLE_EARTH_KML",
  observed_at: null,
  context: {},
};

function apiFor(overrides: Partial<Farm360Api> = {}) {
  return {
    property: vi.fn().mockResolvedValue(property),
    scenes: vi.fn().mockResolvedValue({ items: [] }),
    timeline: vi.fn().mockResolvedValue({ items: [] }),
    assets: vi.fn().mockResolvedValue({ items: [asset] }),
    decisions: vi.fn().mockResolvedValue({ items: [] }),
    tileTemplate: vi.fn(),
    ...overrides,
  } as unknown as Farm360Api;
}

describe("Farm360Page", () => {
  it("keeps the persisted boundary and assets usable when optional context is absent", async () => {
    const api = apiFor();
    render(<Farm360Page api={api} apiBaseUrl="/api" tenantId="tenant-hamilton" propertyId="property-hamilton" token="test" />);
    await act(async () => { await Promise.resolve(); });
    expect(await screen.findByText("Casa hamilton")).toBeInTheDocument();
    expect(screen.getByTestId("property-map")).toHaveTextContent("boundary-ready");
    expect(screen.getByText("Contexto ainda não disponível. Isso não altera os dados confirmados da propriedade.")).toBeInTheDocument();
    expect(screen.getByText("63,87 ha")).toBeInTheDocument();
    expect(screen.queryByText(/não foi possível carregar os dados persistidos/)).not.toBeInTheDocument();
  });

  it("keeps the workspace available when one optional persisted section fails", async () => {
    const api = apiFor({ assets: vi.fn().mockRejectedValue(new Error("asset request failed")) } as Partial<Farm360Api>);
    render(<Farm360Page api={api} apiBaseUrl="/api" tenantId="tenant-hamilton" propertyId="property-hamilton" token="test" />);
    await act(async () => { await Promise.resolve(); });
    expect(await screen.findByText("Sítio Hamilton")).toBeInTheDocument();
    expect(screen.getByTestId("property-map")).toHaveTextContent("boundary-ready");
    expect(screen.getByRole("alert")).toHaveTextContent("SOURCE_UNAVAILABLE");
    expect(screen.queryByText(/não foi possível carregar os dados persistidos/)).not.toBeInTheDocument();
  });
});
