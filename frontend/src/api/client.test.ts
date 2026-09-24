import { describe, expect, it, vi } from "vitest";
import { Farm360Api } from "./client";
import type { PropertyCreate } from "../types/farm360";

describe("Farm360Api", () => {
  it("uses the tenant-scoped contract and bearer session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").products("tenant / id", "property / id");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant%20%2F%20id/properties/property%20%2F%20id/derived-products", { headers: { Authorization: "Bearer session-token" } });
  });

  it("creates a property through the authenticated tenant-scoped contract", async () => {
    const payload: PropertyCreate = { name: "AOI", geometry_geojson: { type: "Polygon", coordinates: [] }, geometry_crs: "EPSG:4326", boundary_source: "MANUAL_CONFIRMED", classification: "MANUAL_CONFIRMED" };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "property-id" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").createProperty("tenant", payload);
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant/properties", { method: "POST", headers: { Authorization: "Bearer session-token", "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  });

  it("loads the portfolio only through the encoded tenant-scoped endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").portfolio("tenant / id");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant%20%2F%20id/portfolio", { headers: { Authorization: "Bearer session-token" } });
  });

  it("loads effective capabilities only from the authenticated tenant endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ permissions: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").access("tenant / id");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant%20%2F%20id/access", { headers: { Authorization: "Bearer session-token" } });
  });

  it("loads Digital Twin assets through the tenant-scoped property endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ property_id: "property", items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").assets("tenant / id", "property / id");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant%20%2F%20id/properties/property%20%2F%20id/assets", { headers: { Authorization: "Bearer session-token" } });
  });

  it("uploads GeoJSON bytes through the tenant-scoped review endpoint without a storage path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "import" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["synthetic_test_data"], "boundary.geojson", { type: "application/geo+json" });
    await new Farm360Api("https://api.example", "session-token").uploadBoundaryImport("tenant", "property", file, "synthetic source", "MANUAL_CONFIRMED", "EPSG:4326");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant/properties/property/boundary-imports", expect.objectContaining({ method: "POST", body: file, headers: expect.objectContaining({ "X-Boundary-Filename": "boundary.geojson", "X-Boundary-CRS": "EPSG:4326" }) }));
  });

  it("labels a KMZ upload with its declared format while retaining the tenant contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "import" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["synthetic_test_kmz"], "boundary.kmz", { type: "application/octet-stream" });
    await new Farm360Api("https://api.example", "session-token").uploadBoundaryImport("tenant", "property", file, "synthetic source", "MANUAL_CONFIRMED", "EPSG:4326");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant/properties/property/boundary-imports", expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/vnd.google-earth.kmz", "X-Boundary-Filename": "boundary.kmz" }) }));
  });
});
