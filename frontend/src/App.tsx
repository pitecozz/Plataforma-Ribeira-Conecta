import { Farm360Api } from "./api/client";
import { oidcConfigurationFromEnvironment } from "./auth/config";
import { OidcSession } from "./auth/OidcSession";
import { PropertyWorkspace } from "./pages/PropertyWorkspace";

const apiUrl = import.meta.env.VITE_RIBEIRA_API_URL;
const tenantId = import.meta.env.VITE_RIBEIRA_TENANT_ID;
const propertyId = import.meta.env.VITE_RIBEIRA_PROPERTY_ID;
const token = import.meta.env.VITE_RIBEIRA_ACCESS_TOKEN;
const authMode = import.meta.env.VITE_RIBEIRA_AUTH_MODE ?? "development";

function workspace(sessionToken: string) {
  return <PropertyWorkspace api={new Farm360Api(apiUrl, sessionToken)} apiBaseUrl={apiUrl} tenantId={tenantId} initialPropertyId={propertyId} token={sessionToken} />;
}

export default function App() {
  if (!apiUrl || !tenantId) return <main className="state">Configuração necessária: informe VITE_RIBEIRA_API_URL e VITE_RIBEIRA_TENANT_ID.</main>;
  if (authMode === "development") {
    if (!token) return <main className="state">Configuração necessária: informe um token de desenvolvimento privado.</main>;
    return workspace(token);
  }
  if (authMode !== "oidc") return <main className="state">Modo de autenticação inválido.</main>;
  try {
    const oidcConfiguration = oidcConfigurationFromEnvironment({
      VITE_RIBEIRA_OIDC_AUDIENCE: import.meta.env.VITE_RIBEIRA_OIDC_AUDIENCE,
      VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT: import.meta.env.VITE_RIBEIRA_OIDC_AUTHORIZATION_ENDPOINT,
      VITE_RIBEIRA_OIDC_CLIENT_ID: import.meta.env.VITE_RIBEIRA_OIDC_CLIENT_ID,
      VITE_RIBEIRA_OIDC_REDIRECT_URI: import.meta.env.VITE_RIBEIRA_OIDC_REDIRECT_URI,
      VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT: import.meta.env.VITE_RIBEIRA_OIDC_TOKEN_ENDPOINT,
    });
    return <OidcSession config={oidcConfiguration}>{workspace}</OidcSession>;
  } catch {
    return <main className="state">Configuração OIDC necessária.</main>;
  }
}
