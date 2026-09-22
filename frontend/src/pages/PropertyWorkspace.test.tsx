import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Farm360Api } from "../api/client";
import type { PortfolioProperty } from "../types/farm360";
import { PropertyWorkspace } from "./PropertyWorkspace";

vi.mock("../features/map/MapCanvas", () => ({ MapCanvas: () => <div data-testid="portfolio-map" /> }));
vi.mock("./Farm360Page", () => ({ Farm360Page: ({ propertyId }: { propertyId: string }) => <div>Farm 360: {propertyId}</div> }));

afterEach(cleanup);

const property = (id: string, name: string): PortfolioProperty => ({
  id, name, tenant_id: "tenant", geometry_geojson: null, geometry_crs: null,
  boundary_source: null, area_hectares: null, classification: "UNKNOWN",
  created_at: "2026-01-01T00:00:00Z", updated_at: null, data_status: "UNKNOWN",
  latest_scene_at: null, latest_ndvi_at: null, latest_ndvi_id: null,
  provenance_available: false, jobs: {},
});

function apiFor(items: PortfolioProperty[] | Promise<PortfolioProperty[]>) {
  return {
    portfolio: vi.fn().mockImplementation(async () => ({ items: await items })),
  } as unknown as Farm360Api;
}

describe("PropertyWorkspace portfolio flow", () => {
  it("shows loading, UNKNOWN fields, the validation label, and switches Farm 360 property", async () => {
    let resolve!: (items: PortfolioProperty[]) => void;
    const pending = new Promise<PortfolioProperty[]>(done => { resolve = done; });
    const api = apiFor(pending);
    render(<PropertyWorkspace api={api} apiBaseUrl="http://api" tenantId="tenant" token="test" />);
    expect(screen.getByText("Carregando portfólio…")).toBeInTheDocument();
    await act(async () => { resolve([property("one", "TEST_AOI_ONLY"), property("two", "Outra propriedade")]); });
    expect(await screen.findByText("Área de validação")).toBeInTheDocument();
    expect(screen.getByText("Consulte os dados confirmados da sua propriedade e as análises disponíveis.")).toBeInTheDocument();
    expect(screen.queryByText("TEST_AOI_ONLY permanece dado de validação.", { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByText("Nova propriedade GeoJSON")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Área de validação/ }));
    expect(screen.getByText("Farm 360: one")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Outra propriedade/ }));
    expect(screen.getByText("Farm 360: two")).toBeInTheDocument();
  });

  it("represents empty, unavailable, and removed selections without retaining stale Farm 360 state", async () => {
    const emptyApi = apiFor([]);
    const { unmount } = render(<PropertyWorkspace api={emptyApi} apiBaseUrl="http://api" tenantId="tenant" token="test" initialPropertyId="removed" />);
    expect(await screen.findByText("Nenhuma propriedade disponível.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Farm 360:/)).not.toBeInTheDocument());
    unmount();

    const unavailable = {
      portfolio: vi.fn().mockRejectedValue(new Error("unavailable")),
    } as unknown as Farm360Api;
    render(<PropertyWorkspace api={unavailable} apiBaseUrl="http://api" tenantId="tenant" token="test" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("SOURCE_UNAVAILABLE");
  });
});
