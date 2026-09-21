import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetPanel } from "./AssetPanel";
import type { DigitalTwinAsset } from "../../types/farm360";

const asset: DigitalTwinAsset = {
  id: "asset-1",
  tenant_id: "tenant",
  asset_type: "RAIN_GAUGE",
  name: "Gauge A",
  serial_number: null,
  status: "ACTIVE",
  property_id: "property",
  site_id: null,
  classification: "MANUAL_CONFIRMED",
  geometry_geojson: { type: "Point", coordinates: [-47, -24] },
  geometry_crs: "EPSG:4326",
  source_reference: "installation survey",
  observed_at: "2026-09-22T12:00:00+00:00",
  context: { calibration_state: "UNKNOWN" },
};

describe("AssetPanel", () => {
  it("keeps an empty inventory explicit", () => {
    render(
      <AssetPanel assets={[]} selectedAssetId={null} onSelect={vi.fn()} />,
    );
    expect(screen.getByText(/nenhum ativo confirmado/i)).toBeInTheDocument();
  });

  it("shows persisted source, classification and context only after selection", () => {
    const select = vi.fn();
    const { rerender } = render(
      <AssetPanel assets={[asset]} selectedAssetId={null} onSelect={select} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Gauge A/ }));
    expect(select).toHaveBeenCalledWith("asset-1");
    rerender(
      <AssetPanel
        assets={[asset]}
        selectedAssetId="asset-1"
        onSelect={select}
      />,
    );
    expect(screen.getByText("installation survey")).toBeInTheDocument();
    expect(screen.getByText("MANUAL_CONFIRMED")).toBeInTheDocument();
    expect(screen.getByText("calibration_state")).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
  });
});
