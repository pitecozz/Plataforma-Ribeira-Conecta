import { describe, expect, it } from "vitest";
import { canRenderNdvi } from "./layerState";
import type { NdviProduct } from "../../types/farm360";

const product = { processing_status: "SUCCEEDED", checksum: "abc" } as NdviProduct;
describe("NDVI layer state", () => {
  it("requires a successful persisted raster and an enabled toggle", () => {
    expect(canRenderNdvi(product, true)).toBe(true);
    expect(canRenderNdvi(product, false)).toBe(false);
    expect(canRenderNdvi({ ...product, checksum: null }, true)).toBe(false);
  });
});
