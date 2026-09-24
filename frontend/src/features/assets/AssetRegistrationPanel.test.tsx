import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Farm360Api } from "../../api/client";
import { AssetRegistrationPanel } from "./AssetRegistrationPanel";

const createdAsset = {
  id: "asset-1", tenant_id: "tenant", asset_type: "RAIN_GAUGE", name: "Gauge A",
  serial_number: null, status: "ACTIVE", property_id: "property", site_id: null,
  classification: "MANUAL_CONFIRMED", geometry_geojson: { type: "Point", coordinates: [-47, -24] },
  geometry_crs: "EPSG:4326", source_reference: "field survey", observed_at: "2026-09-24T10:00:00Z", context: {},
};

afterEach(cleanup);

describe("AssetRegistrationPanel", () => {
  it("posts only explicit factual fields and returns the persisted asset to Farm360", async () => {
    const registerAsset = vi.fn().mockResolvedValue(createdAsset);
    const onCreated = vi.fn();
    render(<AssetRegistrationPanel api={{ registerAsset } as unknown as Farm360Api} tenantId="tenant" propertyId="property" onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText("Nome do ativo"), { target: { value: "Gauge A" } });
    fireEvent.change(screen.getByLabelText("Tipo técnico"), { target: { value: "RAIN_GAUGE" } });
    fireEvent.change(screen.getByLabelText("Fonte ou referência de confirmação"), { target: { value: "field survey" } });
    fireEvent.change(screen.getByLabelText("Observado em"), { target: { value: "2026-09-24T12:00" } });
    fireEvent.change(screen.getByLabelText("Longitude do ativo"), { target: { value: "-47" } });
    fireEvent.change(screen.getByLabelText("Latitude do ativo"), { target: { value: "-24" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar ativo" }));
    await waitFor(() => expect(registerAsset).toHaveBeenCalledTimes(1));
    expect(registerAsset).toHaveBeenCalledWith("tenant", expect.objectContaining({ property_id: "property", geometry: { type: "Point", coordinates: [-47, -24] }, geometry_crs: "EPSG:4326", source_reference: "field survey", classification: "MANUAL_CONFIRMED", context: {} }));
    expect(onCreated).toHaveBeenCalledWith(createdAsset);
    expect(screen.getByRole("alert")).toHaveTextContent("Ativo confirmado e vinculado à propriedade.");
  });

  it("keeps incomplete coordinates from becoming a persisted location", () => {
    const registerAsset = vi.fn();
    render(<AssetRegistrationPanel api={{ registerAsset } as unknown as Farm360Api} tenantId="tenant" propertyId="property" onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Nome do ativo"), { target: { value: "Gauge A" } });
    fireEvent.change(screen.getByLabelText("Tipo técnico"), { target: { value: "RAIN_GAUGE" } });
    fireEvent.change(screen.getByLabelText("Fonte ou referência de confirmação"), { target: { value: "field survey" } });
    fireEvent.change(screen.getByLabelText("Observado em"), { target: { value: "2026-09-24T12:00" } });
    fireEvent.change(screen.getByLabelText("Longitude do ativo"), { target: { value: "-47" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar ativo" }));
    expect(registerAsset).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("DADO_INSUFICIENTE");
  });
});
