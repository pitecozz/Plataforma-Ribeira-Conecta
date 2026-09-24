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
  evidence_id: "evidence-1",
};

describe("AssetPanel", () => {
  it("keeps an empty inventory explicit", () => {
    render(
      <AssetPanel assets={[]} selectedAssetId={null} onSelect={vi.fn()} />,
    );
    expect(screen.getByText(/ainda não há ativos confirmados/i)).toBeInTheDocument();
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
    expect(screen.getAllByText("installation survey")).toHaveLength(2);
    expect(screen.getByText("Confirmado")).toBeInTheDocument();
    expect(screen.getByText("calibration_state")).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("evidence-1")).toBeInTheDocument();
  });

  it("keeps asset rule evaluation hidden without the two required read permissions", () => {
    render(<AssetPanel assets={[asset]} selectedAssetId="asset-1" onSelect={vi.fn()} api={{} as never} tenantId="tenant" onEvaluated={vi.fn()} />);
    expect(screen.queryByText("Avaliar regras para este ativo")).not.toBeInTheDocument();
  });

  it("evaluates an evidenced asset only after an explicit user action and refreshes decisions", async () => {
    const evaluateAsset = vi.fn().mockResolvedValue({ decision: { id: "decision-1" } });
    const onEvaluated = vi.fn().mockResolvedValue(undefined);
    render(<AssetPanel assets={[asset]} selectedAssetId="asset-1" onSelect={vi.fn()} api={{ evaluateAsset } as never} tenantId="tenant" canEvaluateAssets onEvaluated={onEvaluated} />);
    fireEvent.click(screen.getByText("Avaliar regras para este ativo"));
    fireEvent.click(screen.getByRole("button", { name: "Avaliar evidências e regras" }));
    expect(evaluateAsset).toHaveBeenCalledWith("tenant", "asset-1");
    await screen.findByText(/Avaliação registrada no histórico/i);
    expect(onEvaluated).toHaveBeenCalledTimes(1);
  });
});
