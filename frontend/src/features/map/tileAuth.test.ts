import { describe, expect, it } from "vitest";
import { transformMapRequest } from "./tileAuth";

const api = "http://127.0.0.1:8080";
const token = "dev-test-token";

describe("MapLibre request authentication", () => {
  it("adds Authorization only to the exact Ribeira derived-product tile route", () => {
    expect(
      transformMapRequest(
        "http://127.0.0.1:8080/v1/tenants/tenant-1/derived-products/product-1/tiles/13/3026/4658",
        api,
        token,
      ),
    ).toEqual({
      url: "http://127.0.0.1:8080/v1/tenants/tenant-1/derived-products/product-1/tiles/13/3026/4658",
      headers: { Authorization: "Bearer dev-test-token" },
    });
  });

  it("does not add Authorization to the external visual basemap", () => {
    expect(
      transformMapRequest(
        "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        api,
        token,
      ),
    ).toEqual({ url: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" });
  });

  it("does not add Authorization to another external origin", () => {
    expect(
      transformMapRequest("https://example.invalid/tiles/13/3026/4658", api, token),
    ).toEqual({ url: "https://example.invalid/tiles/13/3026/4658" });
  });
});
