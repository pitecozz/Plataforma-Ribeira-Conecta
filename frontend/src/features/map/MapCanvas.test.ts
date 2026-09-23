import { describe, expect, it } from "vitest";

import { assetMarkerSymbol, boundsForGeometry } from "./mapPresentation";

describe("property map presentation", () => {
  it("derives fit bounds from the persisted property geometry", () => {
    expect(
      boundsForGeometry({
        type: "Polygon",
        coordinates: [[[-47.2, -24.1], [-46.9, -24.1], [-46.9, -24.4], [-47.2, -24.1]]],
      }),
    ).toEqual([-47.2, -24.4, -46.9, -24.1]);
  });

  it("handles geometry collections without guessing an extent", () => {
    expect(
      boundsForGeometry({
        type: "GeometryCollection",
        geometries: [
          { type: "Point", coordinates: [-47, -24] },
          { type: "Point", coordinates: [-46.8, -24.3] },
        ],
      }),
    ).toEqual([-47, -24.3, -46.8, -24]);
  });

  it("uses recognizable markers while retaining canonical asset types", () => {
    expect(assetMarkerSymbol("house_building")).toBe("⌂");
    expect(assetMarkerSymbol("shed")).toBe("▰");
    expect(assetMarkerSymbol("camera")).toBe("◉");
  });
});
