import { describe, expect, it } from "vitest";

import { formatHectares } from "./formatting";
import { customerAssetTypeLabel, customerSourceLabel } from "./presentation";

describe("formatHectares", () => {
  it("rounds customer-facing area without changing the persisted value", () => {
    expect(formatHectares("63.86741722620799")).toBe("63,87");
    expect(formatHectares("12.5")).toBe("12,5");
  });

  it("does not turn missing or malformed values into a number", () => {
    expect(formatHectares(null)).toBeNull();
    expect(formatHectares("not-an-area")).toBeNull();
  });
});

describe("customer-facing provenance labels", () => {
  it("does not expose import hashes as an asset source", () => {
    expect(customerSourceLabel("manifest_sha256=abc geojson_sha256=def")).toBe(
      "Dado fornecido pelo proprietário (Google Earth)",
    );
  });

  it("translates canonical and legacy asset type spellings", () => {
    expect(customerAssetTypeLabel("shed")).toBe("Barracão");
    expect(customerAssetTypeLabel("camera")).toBe("Câmera");
    expect(customerAssetTypeLabel("house building")).toBe("Casa / edificação");
  });
});
