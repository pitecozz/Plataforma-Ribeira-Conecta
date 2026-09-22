import { expect, test } from "@playwright/test";

const expectedOidcHost = process.env.RIBEIRA_PLAYWRIGHT_OIDC_HOST;
const pilotTenantId = process.env.RIBEIRA_PLAYWRIGHT_TENANT_ID;

test("public pilot ingress is OIDC-gated and keeps private services private", async ({ page, request }, testInfo) => {
  const configuredBaseUrl = testInfo.project.use.baseURL;
  if (!configuredBaseUrl || !expectedOidcHost) {
    throw new Error("RIBEIRA_PLAYWRIGHT_BASE_URL and RIBEIRA_PLAYWRIGHT_OIDC_HOST are required");
  }
  const publicOrigin = new URL(configuredBaseUrl).origin;
  expect(publicOrigin).toMatch(/^https:\/\//);

  await expect.poll(async () => (await request.get("/api/health/live")).status()).toBe(200);
  await expect.poll(async () => (await request.get("/api/health/ready")).status()).toBe(200);
  for (const privatePath of ["/metrics", "/api/metrics", "/api/docs", "/api/openapi.json", "/api/redoc"]) {
    expect((await request.get(privatePath)).status()).toBe(404);
  }

  if (pilotTenantId) {
    const unauthorized = await request.get(`/api/v1/tenants/${encodeURIComponent(pilotTenantId)}/portfolio`);
    expect(unauthorized.status()).toBe(401);
  }

  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();

  const isAuthorizationRequest = (candidateUrl: string) => {
    const url = new URL(candidateUrl);
    return url.hostname === expectedOidcHost && url.pathname === "/authorize";
  };
  const authorizationRequestPromise = page.waitForRequest((candidate) => {
    const url = new URL(candidate.url());
    return candidate.isNavigationRequest() && url.hostname === expectedOidcHost && url.pathname === "/authorize";
  });
  const authorizationResponsePromise = page.waitForResponse((candidate) => isAuthorizationRequest(candidate.url()));
  await page.getByRole("button", { name: "Entrar" }).click();
  const authorizationRequest = await authorizationRequestPromise;
  const authorizationResponse = await authorizationResponsePromise;
  const authorizationUrl = new URL(authorizationRequest.url());

  expect(authorizationResponse.status()).toBeLessThan(400);
  expect(authorizationUrl.protocol).toBe("https:");
  expect(authorizationUrl.hostname).toBe(expectedOidcHost);
  expect(authorizationUrl.searchParams.get("response_type")).toBe("code");
  expect(authorizationUrl.searchParams.get("client_id")).toBeTruthy();
  expect(authorizationUrl.searchParams.get("redirect_uri")).toBe(`${publicOrigin}/`);
  expect(authorizationUrl.searchParams.get("scope")).toContain("openid");
  expect(authorizationUrl.searchParams.get("state")).toBeTruthy();
  expect(authorizationUrl.searchParams.get("code_challenge")).toBeTruthy();
  expect(authorizationUrl.searchParams.get("code_challenge_method")).toBe("S256");
  expect(authorizationUrl.searchParams.get("audience")).toBeTruthy();
});
