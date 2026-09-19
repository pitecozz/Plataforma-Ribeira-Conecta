export type OidcBrowserConfiguration = {
  audience?: string;
  authorizationEndpoint: string;
  clientId: string;
  redirectUri: string;
  scope: string;
  tokenEndpoint: string;
};

const verifierKey = "ribeira.oidc.pkce.verifier";
const stateKey = "ribeira.oidc.state";

function randomUrlSafe(bytes: Uint8Array): string {
  let raw = "";
  bytes.forEach((value) => { raw += String.fromCharCode(value); });
  return btoa(raw).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return randomUrlSafe(new Uint8Array(digest));
}

export async function oidcAuthorizationUrl(config: OidcBrowserConfiguration): Promise<string> {
  const verifier = randomUrlSafe(crypto.getRandomValues(new Uint8Array(48)));
  const state = randomUrlSafe(crypto.getRandomValues(new Uint8Array(24)));
  sessionStorage.setItem(verifierKey, verifier);
  sessionStorage.setItem(stateKey, state);
  const url = new URL(config.authorizationEndpoint);
  const parameters = new URLSearchParams({
    response_type: "code",
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: config.scope,
    state,
    code_challenge: await challenge(verifier),
    code_challenge_method: "S256",
  });
  if (config.audience) parameters.set("audience", config.audience);
  url.search = parameters.toString();
  return url.toString();
}

export async function exchangeAuthorizationCode(
  config: OidcBrowserConfiguration,
  code: string,
  state: string | null,
): Promise<string> {
  const expectedState = sessionStorage.getItem(stateKey);
  const verifier = sessionStorage.getItem(verifierKey);
  if (!expectedState || !verifier || state !== expectedState) {
    throw new Error("OIDC state validation failed");
  }
  const response = await fetch(config.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    }),
  });
  sessionStorage.removeItem(verifierKey);
  sessionStorage.removeItem(stateKey);
  if (!response.ok) throw new Error("OIDC token exchange failed");
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || typeof (payload as { access_token?: unknown }).access_token !== "string") {
    throw new Error("OIDC token response has no access token");
  }
  return (payload as { access_token: string }).access_token;
}
