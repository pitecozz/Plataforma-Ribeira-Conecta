import type { OidcBrowserConfiguration } from "./oidc";
import { redirectUriFromEnvironment } from "../pilotOrigin";

type OidcEnvironment = {
  VITE_RIBEIRA_OIDC_AUDIENCE?: string;
  VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT?: string;
  VITE_RIBEIRA_OIDC_CLIENT_ID?: string;
  VITE_RIBEIRA_OIDC_REDIRECT_URI?: string;
  VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT?: string;
  VITE_RIBEIRA_PUBLIC_ORIGIN?: string;
};

export function oidcConfigurationFromEnvironment(environment: OidcEnvironment): OidcBrowserConfiguration {
  const audience = environment.VITE_RIBEIRA_OIDC_AUDIENCE;
  const authorizationEndpoint = environment.VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT;
  const clientId = environment.VITE_RIBEIRA_OIDC_CLIENT_ID;
  const redirectUri = redirectUriFromEnvironment(environment);
  const tokenEndpoint = environment.VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT;
  if (!audience || !authorizationEndpoint || !clientId || !redirectUri || !tokenEndpoint) {
    throw new Error("OIDC configuration requires audience, authorization endpoint, token endpoint, client ID, and redirect URI");
  }
  return { audience, authorizationEndpoint, clientId, redirectUri, scope: "openid profile email", tokenEndpoint };
}
