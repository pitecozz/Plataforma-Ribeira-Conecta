import { beforeEach, describe, expect, it, vi } from "vitest";
import { oidcAuthorizationUrl } from "./oidc";

describe("OIDC Authorization Code + PKCE", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", {
      getRandomValues: (values: Uint8Array) => values.fill(7),
      subtle: { digest: async () => new Uint8Array(32).fill(8).buffer },
    });
  });

  it("creates an authorization-code request without a client secret", async () => {
    const url = new URL(await oidcAuthorizationUrl({
      authorizationEndpoint: "https://issuer.example/authorize",
      tokenEndpoint: "https://issuer.example/token",
      clientId: "ribeira-spa",
      redirectUri: "http://127.0.0.1:5173/",
      scope: "openid profile",
    }));
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("client_secret")).toBeNull();
    expect(sessionStorage.getItem("ribeira.oidc.pkce.verifier")).toBeTruthy();
  });
});
