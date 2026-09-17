import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TemporalPanel } from "./TemporalPanel";
import type { TimelineItem } from "../../types/farm360";

const items = [
  { scene_internal_id: "scene-a", scene_id: "S2-A", provider: "CDSE", collection: "sentinel-2-l2a", acquisition_datetime: "2025-01-01T10:00:00Z", cloud_cover: "5", provenance_available: true, derived_product: { id: "product-a", processing_status: "SUCCEEDED", statistics: { coverage_percentage: "90" } } },
  { scene_internal_id: "scene-b", scene_id: "S2-B", provider: "CDSE", collection: "sentinel-2-l2a", acquisition_datetime: "2025-02-01T10:00:00Z", cloud_cover: null, provenance_available: true, derived_product: { id: "product-b", processing_status: "SUCCEEDED", statistics: { coverage_percentage: "80" } } },
] as TimelineItem[];

describe("TemporalPanel", () => {
  it("selects a dated product and exposes non-causal aggregate comparison", () => {
    const onSelectProduct = vi.fn();
    const onModeChange = vi.fn();
    render(<TemporalPanel items={items} selectedProductId="product-b" mode="view" baselineProductId="product-a" targetProductId="product-b" comparison={null} comparisonLoading={false} onSelectProduct={onSelectProduct} onModeChange={onModeChange} onBaselineChange={vi.fn()} onTargetChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /1 de jan/i }));
    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));
    expect(onSelectProduct).toHaveBeenCalledWith("product-a");
    expect(onModeChange).toHaveBeenCalledWith("compare");
  });

  it("shows insufficient comparison without inventing comparable pixels", () => {
    render(<TemporalPanel items={items} selectedProductId="product-b" mode="compare" baselineProductId="product-a" targetProductId="product-b" comparison={{ property_id: "property", status: "DADO_INSUFICIENTE", baseline: items[0].derived_product, target: items[1].derived_product, comparison: { delta_mean: null, comparable_valid_pixels: null, comparable_coverage_percentage: null, classification: "INCONCLUSIVE", delta_product_id: null, delta_minimum: null, delta_maximum: null, delta_median: null, quality_mask_policy: null, alignment_summary: null, limitations: ["No pixel-aligned delta raster"] } }} comparisonLoading={false} onSelectProduct={vi.fn()} onModeChange={vi.fn()} onBaselineChange={vi.fn()} onTargetChange={vi.fn()} />);
    expect(screen.getByText("DADO_INSUFICIENTE")).toBeInTheDocument();
    expect(screen.getAllByText("NULL").length).toBeGreaterThan(1);
    expect(screen.getByText("No pixel-aligned delta raster")).toBeInTheDocument();
  });
});
