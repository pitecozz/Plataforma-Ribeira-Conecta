import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DataAvailabilityPanel } from "./DataAvailabilityPanel";
import type { FieldContext, PropertyRecord } from "../../types/farm360";

const property: PropertyRecord = {
  id: "property", tenant_id: "tenant", name: "Synthetic property",
  geometry_geojson: null, geometry_crs: null, boundary_source: null,
  area_hectares: null, classification: "UNKNOWN", created_at: "2026-09-24T00:00:00Z",
  data_status: "UNKNOWN",
};

const field: FieldContext = {
  id: "field", tenant_id: "tenant", property_id: "property", name: "Synthetic field",
  status: "ACTIVE", geometry_geojson: { type: "Polygon", coordinates: [] },
  geometry_crs: "EPSG:4326", boundary_version: 1, boundary_checksum: "a".repeat(64),
  source_reference: "synthetic_test_data", observed_at: "2026-09-24T00:00:00Z",
  classification: "MANUAL_CONFIRMED", created_at: "2026-09-24T00:00:00Z",
};

afterEach(cleanup);

describe("DataAvailabilityPanel", () => {
  it("keeps a missing field inventory explicit", () => {
    render(<DataAvailabilityPanel property={property} assets={[]} fields={[]} scenes={[]} timeline={[]} />);
    expect(screen.getByText("Talhões operacionais")).toBeInTheDocument();
    expect(screen.getByText("Nenhum talhão operacional registrado")).toBeInTheDocument();
    expect(screen.getByText("Talhões operacionais").closest("li")).toHaveTextContent("Aguardando dados");
  });

  it("keeps a failed field inventory distinct from a confirmed empty inventory", () => {
    render(<DataAvailabilityPanel property={property} assets={[]} fields={[]} scenes={[]} timeline={[]} fieldsUnavailable />);
    expect(screen.getByText("Inventário de talhões indisponível nesta consulta")).toBeInTheDocument();
    expect(screen.getByText("Talhões operacionais").closest("li")).toHaveTextContent("Parcial");
    expect(screen.queryByText("Nenhum talhão operacional registrado")).not.toBeInTheDocument();
  });

  it("reports only the confirmed count and provenance/time availability", () => {
    render(<DataAvailabilityPanel property={property} assets={[]} fields={[field]} scenes={[]} timeline={[]} />);
    expect(screen.getByText("1 talhão(ões) com fonte e tempo registrados")).toBeInTheDocument();
    expect(screen.getByText("Disponível")).toBeInTheDocument();
  });
});
