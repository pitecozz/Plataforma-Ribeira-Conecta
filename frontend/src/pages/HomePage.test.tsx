import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomePage } from "./HomePage";
import type { Farm360Api } from "../api/client";

const property = {
  id: "property-1", tenant_id: "tenant", name: "Sítio Piloto", geometry_geojson: null,
  geometry_crs: null, boundary_source: "MANUAL_CONFIRMED", area_hectares: "12.5",
  classification: "MANUAL_CONFIRMED", created_at: "2026-09-22T00:00:00Z",
  data_status: "DADO_INSUFICIENTE", latest_scene_at: null, latest_ndvi_at: null,
  latest_ndvi_id: null, provenance_available: false, jobs: {},
};

describe("HomePage", () => {
  it("shows only returned portfolio values and opens the selected Farm360 property", async () => {
    const api = { portfolio: vi.fn().mockResolvedValue({ items: [property] }) } as unknown as Farm360Api;
    const openFarm360 = vi.fn();
    render(<HomePage api={api} tenantId="tenant" onOpenFarm360={openFarm360} />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Sítio Piloto")).toBeInTheDocument();
    expect(screen.getByText("DADO_INSUFICIENTE")).toBeInTheDocument();
    expect(screen.getAllByText("UNKNOWN")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Abrir Farm360" }));
    expect(openFarm360).toHaveBeenCalledWith("property-1");
  });
});
