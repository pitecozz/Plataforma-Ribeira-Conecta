import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenancePanel } from "./ProvenancePanel";
import type { Provenance } from "../../types/farm360";

const provenance = { product: { id: "product-1", checksum: "checksum" }, processing_job: { id: "job-1", status: "SUCCEEDED" }, assets: [{ id: "a", asset_key: "B04_10m", checksum: "red-checksum" }, { id: "b", asset_key: "B08_10m", checksum: "nir-checksum" }], scene: { scene_id: "S2A_REAL" }, provider: { id: "COPERNICUS_CDSE", collection: "sentinel-2-l2a", catalog_source: "COPERNICUS_CDSE_STAC" }, evidence: [] } as unknown as Provenance;
describe("Evidence Chain", () => { it("renders the persisted derivation path", () => { render(<ProvenancePanel provenance={provenance} />); expect(screen.getByText(/Derived Product/)).toBeInTheDocument(); expect(screen.getByText("S2A_REAL")).toBeInTheDocument(); expect(screen.getByText(/B04_10m \(red-checksum\), B08_10m \(nir-checksum\)/)).toBeInTheDocument(); }); });

it("labels delta inputs as upstream products and scenes", () => {
  const delta = { ...provenance, product: { ...provenance.product, product_type: "NDVI_DELTA", algorithm_id: "NDVI_TEMPORAL_DELTA", formula: "NDVI_target - NDVI_baseline" }, assets: [], upstreams: [{ relationship: "BASELINE_NDVI", product: { id: "baseline" }, scene: { scene_id: "S2_BASELINE" }, assets: [{ asset_key: "B04_10m", checksum: "baseline-red" }, { asset_key: "B08_10m", checksum: "baseline-nir" }, { asset_key: "SCL_20m", checksum: "baseline-scl" }] }, { relationship: "TARGET_NDVI", product: { id: "target" }, scene: { scene_id: "S2_TARGET" }, assets: [{ asset_key: "B04_10m", checksum: "target-red" }, { asset_key: "B08_10m", checksum: "target-nir" }, { asset_key: "SCL_20m", checksum: "target-scl" }] }] } as unknown as Provenance;
  render(<ProvenancePanel provenance={delta} />);
  expect(screen.getByText("Inputs diretos")).toBeInTheDocument();
  expect(screen.getByText("Produtos derivados upstream")).toBeInTheDocument();
  expect(screen.getByText("Sentinel scenes upstream")).toBeInTheDocument();
  expect(screen.getByText("S2_BASELINE · S2_TARGET")).toBeInTheDocument();
  expect(screen.getByText(/B04_10m \(baseline-red\)/)).toBeInTheDocument();
  expect(screen.queryByText("DADO_INSUFICIENTE")).not.toBeInTheDocument();
});
