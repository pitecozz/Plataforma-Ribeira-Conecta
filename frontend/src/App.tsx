import { Farm360Api } from "./api/client";
import { PropertyWorkspace } from "./pages/PropertyWorkspace";

const apiUrl = import.meta.env.VITE_RIBEIRA_API_URL;
const tenantId = import.meta.env.VITE_RIBEIRA_TENANT_ID;
const propertyId = import.meta.env.VITE_RIBEIRA_PROPERTY_ID;
const token = import.meta.env.VITE_RIBEIRA_ACCESS_TOKEN;

export default function App() {
  if (!apiUrl || !tenantId || !token) return <main className="state">Configuração necessária: informe VITE_RIBEIRA_API_URL, VITE_RIBEIRA_TENANT_ID e um token de sessão.</main>;
  return <PropertyWorkspace api={new Farm360Api(apiUrl, token)} apiBaseUrl={apiUrl} tenantId={tenantId} initialPropertyId={propertyId} token={token} />;
}
