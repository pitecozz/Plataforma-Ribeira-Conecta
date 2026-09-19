import { beforeEach, describe, expect, it, vi } from "vitest";
import { oidcConfigurationFromEnvironment } from "./config";
import { exchangeAuthorizationCode, oidcAuthorizationUrl } from "./oidc";

describe("OIDC Authorization Code + PKCE", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", {
      getRandomValues: (values: Uint8Array) => values.fill(7),
      subtle: { digest: async () => new Uint8Array(32).fill(8).buffer },
    });
  });

  it("creates an authorization-code request with audience and PKCE without a client secret", async () => {
    const url = new URL(await oidcAuthorizationUrl({
      audience: "https://api.example/audience with space",
      authorizationEndpoint: "https://issuer.example/authorize",
      tokenEndpoint: "https://issuer.example/token",
      clientId: "ribeira-spa",
      redirectUri: "http://127.0.0.1:5173/",
      scope: "openid profile",
    }));
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("audience")).toBe("https://api.example/audience with space");
    expect(url.search).toContain("audience=https%3A%2F%2Fapi.example%2Faudience+with+space");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("state")).toBeTruthy();
    expect(url.searchParams.get("redirect_uri")).toBe("http://127.0.0.1:5173/");
    expect(url.searchParams.get("client_secret")).toBeNull();
    expect(sessionStorage.getItem("ribeira.oidc.pkce.verifier")).toBeTruthy();
  });

  it("fails explicitly when protected OIDC configuration has no audience", () => {
    expect(() => oidcConfigurationFromEnvironment({
      VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT: "https://issuer.example/authorize",
      VITE_RIBEIRA_OIDC_CLIENT_ID: "ribeira-spa",
      VITE_RIBEIRA_OIDC_REDIRECT_URI: "http://127.0.0.1:5173/",
      VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT: "https://issuer.example/token",
    })).toThrow(/audience/i);
  });

  it("exchanges the authorization code with PKCE and no client secret", async () => {
    await oidcAuthorizationUrl({
      audience: "https://api.example",
      authorizationEndpoint: "https://issuer.example/authorize",
      clientId: "ribeira-spa",
      redirectUri: "http://127.0.0.1:5173/",
      scope: "openid profile email",
      tokenEndpoint: "https://issuer.example/token",
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: "test-access-token" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(exchangeAuthorizationCode({
      audience: "https://api.example",
      authorizationEndpoint: "https://issuer.example/authorize",
      clientId: "ribeira-spa",
      redirectUri: "http://127.0.0.1:5173/",
      scope: "openid profile email",
      tokenEndpoint: "https://issuer.example/token",
    }, "authorization-code", sessionStorage.getItem("ribeira.oidc.state"))).resolves.toBe("test-access-token");

    const request = fetchMock.mock.calls[0];
    expect(request[0]).toBe("https://issuer.example/token");
    const body = new URLSearchParams((request[1] as RequestInit).body as string);
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("client_id")).toBe("ribeira-spa");
    expect(body.get("code")).toBe("authorization-code");
    expect(body.get("code_verifier")).toBeTruthy();
    expect(body.get("redirect_uri")).toBe("http://127.0.0.1:5173/");
    expect(body.get("client_secret")).toBeNull();
  });
});
