import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NdviPanel } from "./NdviPanel";
import type { NdviProduct } from "../../types/farm360";

const product = { statistics: { minimum: "0.1", maximum: "0.8", mean: "0.4", median: "0.4", valid_count: 12, nodata_count: 3, coverage_percentage: "80" }, checksum: "sha256", generated_at: "2026-01-01T00:00:00Z", processing_status: "SUCCEEDED" } as NdviProduct;
describe("NDVI metadata", () => { it("shows persisted statistics without inventing missing values", () => { render(<NdviPanel product={product} />); expect(screen.getByText("0.1 / 0.8 / 0.4")).toBeInTheDocument(); expect(screen.getByText("12")).toBeInTheDocument(); expect(screen.getByText("3")).toBeInTheDocument(); }); });
