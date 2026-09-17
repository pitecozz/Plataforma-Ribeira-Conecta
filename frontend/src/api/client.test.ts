import { describe, expect, it, vi } from "vitest";
import { Farm360Api } from "./client";

describe("Farm360Api", () => {
  it("uses the tenant-scoped contract and bearer session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new Farm360Api("https://api.example", "session-token").products("tenant / id", "property / id");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/v1/tenants/tenant%20%2F%20id/properties/property%20%2F%20id/derived-products", { headers: { Authorization: "Bearer session-token" } });
  });
});
