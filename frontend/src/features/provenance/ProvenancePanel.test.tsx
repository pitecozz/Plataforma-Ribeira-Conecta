import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenancePanel } from "./ProvenancePanel";
import type { Provenance } from "../../types/farm360";

const provenance = { product: { id: "product-1", checksum: "checksum" }, processing_job: { id: "job-1", status: "SUCCEEDED" }, assets: [{ id: "a", asset_key: "B04_10m" }, { id: "b", asset_key: "B08_10m" }], scene: { scene_id: "S2A_REAL" }, provider: { id: "COPERNICUS_CDSE", collection: "sentinel-2-l2a", catalog_source: "COPERNICUS_CDSE_STAC" }, evidence: [] } as unknown as Provenance;
describe("Evidence Chain", () => { it("renders the persisted derivation path", () => { render(<ProvenancePanel provenance={provenance} />); expect(screen.getByText(/Derived Product/)).toBeInTheDocument(); expect(screen.getByText("S2A_REAL")).toBeInTheDocument(); expect(screen.getByText(/B04_10m, B08_10m/)).toBeInTheDocument(); }); });
