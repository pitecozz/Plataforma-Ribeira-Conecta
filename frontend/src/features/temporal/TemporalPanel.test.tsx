import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Farm360Api } from "../../api/client";
import type { ProcessingJob, TimelineItem } from "../../types/farm360";
import { TemporalPanel } from "./TemporalPanel";

const items = [
  { scene_internal_id: "scene-a", scene_id: "S2-A", provider: "CDSE", collection: "sentinel-2-l2a", acquisition_datetime: "2025-01-01T10:00:00Z", cloud_cover: "5", provenance_available: true, derived_product: { id: "product-a", product_type: "NDVI", processing_status: "SUCCEEDED", statistics: { coverage_percentage: "90" } } },
  { scene_internal_id: "scene-b", scene_id: "S2-B", provider: "CDSE", collection: "sentinel-2-l2a", acquisition_datetime: "2025-02-01T10:00:00Z", cloud_cover: null, provenance_available: true, derived_product: { id: "product-b", product_type: "NDVI", processing_status: "SUCCEEDED", statistics: { coverage_percentage: "80" } } },
] as TimelineItem[];

const api = {} as Farm360Api;
const common = {
  api,
  tenantId: "tenant",
  propertyId: "property",
  items,
  selectedProductId: "product-b",
  mode: "view" as const,
  baselineProductId: "product-a",
  targetProductId: "product-b",
  comparison: null,
  comparisonLoading: false,
  onChanged: vi.fn().mockResolvedValue(undefined),
  onSelectProduct: vi.fn(),
  onModeChange: vi.fn(),
  onBaselineChange: vi.fn(),
  onTargetChange: vi.fn(),
};

const queued = (id: string, type: string): ProcessingJob => ({
  id,
  job_type: type,
  status: "QUEUED",
  failure_code: null,
  failure_reason: null,
  output_product_id: null,
  attempt: 0,
  max_attempts: 3,
  heartbeat_at: null,
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  finished_at: null,
});

const succeeded = (job: ProcessingJob, productId: string): ProcessingJob => ({
  ...job,
  status: "SUCCEEDED",
  output_product_id: productId,
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TemporalPanel", () => {
  it("selects a dated product and exposes non-causal aggregate comparison", () => {
    const onSelectProduct = vi.fn();
    const onModeChange = vi.fn();
    render(<TemporalPanel {...common} onSelectProduct={onSelectProduct} onModeChange={onModeChange} />);
    fireEvent.click(screen.getByRole("button", { name: /1 de jan/i }));
    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));
    expect(onSelectProduct).toHaveBeenCalledWith("product-a");
    expect(onModeChange).toHaveBeenCalledWith("compare");
  });

  it("shows insufficient comparison without inventing comparable pixels", () => {
    render(<TemporalPanel {...common} mode="compare" comparison={{ property_id: "property", status: "DADO_INSUFICIENTE", baseline: items[0].derived_product, target: items[1].derived_product, comparison: { delta_mean: null, comparable_valid_pixels: null, comparable_coverage_percentage: null, classification: "INCONCLUSIVE", delta_product_id: null, delta_minimum: null, delta_maximum: null, delta_median: null, quality_mask_policy: null, alignment_summary: null, limitations: ["No pixel-aligned delta raster"] } }} />);
    expect(screen.getByText("DADO_INSUFICIENTE")).toBeInTheDocument();
    expect(screen.getByText(/Pixels comparáveis: UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText("No pixel-aligned delta raster")).toBeInTheDocument();
  });

  it("masks both NDVI inputs, creates the delta, polls jobs, and refreshes", async () => {
    vi.useFakeTimers();
    const maskA = queued("mask-a", "QUALITY_MASKED_NDVI");
    const maskB = queued("mask-b", "QUALITY_MASKED_NDVI");
    const delta = queued("delta", "TEMPORAL_DELTA");
    const workflowApi = {
      createQualityMaskedNdviJob: vi.fn()
        .mockResolvedValueOnce(maskA)
        .mockResolvedValueOnce(maskB),
      createTemporalDeltaJob: vi.fn().mockResolvedValue(delta),
      job: vi.fn()
        .mockResolvedValueOnce(succeeded(maskA, "masked-a"))
        .mockResolvedValueOnce(succeeded(maskB, "masked-b"))
        .mockResolvedValueOnce(succeeded(delta, "delta-product")),
    } as unknown as Farm360Api;
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<TemporalPanel {...common} api={workflowApi} mode="compare" canProcess onChanged={onChanged} />);

    fireEvent.click(screen.getByRole("button", { name: /Gerar Δ NDVI/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(workflowApi.createQualityMaskedNdviJob).toHaveBeenNthCalledWith(1, "tenant", "property", "product-a");
    expect(workflowApi.createQualityMaskedNdviJob).toHaveBeenNthCalledWith(2, "tenant", "property", "product-b");
    expect(workflowApi.createTemporalDeltaJob).toHaveBeenCalledWith("tenant", "property", "masked-a", "masked-b");
    expect(onChanged).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("proveniência persistida");
  });

  it("does not expose processing to a read-only viewer", () => {
    render(<TemporalPanel {...common} mode="compare" canProcess={false} />);
    expect(screen.queryByRole("button", { name: /Gerar Δ NDVI/ })).not.toBeInTheDocument();
  });
});
