import { describe, expect, it } from "vitest";

import {
  apiUrlFromEnvironment,
  configuredPublicOrigin,
  redirectUriFromEnvironment,
} from "./pilotOrigin";

describe("pilot public origin", () => {
  const origin = "https://purple-sun-1234.trycloudflare.com";

  it("derives same-origin API and OIDC callback URLs from a Quick Tunnel", () => {
    expect(apiUrlFromEnvironment({ VITE_RIBEIRA_PUBLIC_ORIGIN: origin })).toBe(`${origin}/api`);
    expect(redirectUriFromEnvironment({ VITE_RIBEIRA_PUBLIC_ORIGIN: origin })).toBe(`${origin}/`);
  });

  it("retains explicit API and redirect configuration when supplied", () => {
    expect(apiUrlFromEnvironment({ VITE_RIBEIRA_API_URL: "https://api.example/api", VITE_RIBEIRA_PUBLIC_ORIGIN: origin })).toBe("https://api.example/api");
    expect(redirectUriFromEnvironment({ VITE_RIBEIRA_OIDC_REDIRECT_URI: "https://other.example/", VITE_RIBEIRA_PUBLIC_ORIGIN: origin })).toBe("https://other.example/");
  });

  it("rejects an origin with an unsafe scheme or path", () => {
    expect(() => configuredPublicOrigin("http://example.test")).toThrow("HTTPS origin");
    expect(() => configuredPublicOrigin("https://example.test/callback")).toThrow("without a path");
  });
});
