import { Farm360Api } from "./api/client";
import { Farm360Page } from "./pages/Farm360Page";

const apiUrl = import.meta.env.VITE_RIBEIRA_API_URL;
const tenantId = import.meta.env.VITE_RIBEIRA_TENANT_ID;
const propertyId = import.meta.env.VITE_RIBEIRA_PROPERTY_ID;
const token = import.meta.env.VITE_RIBEIRA_ACCESS_TOKEN;

export default function App() {
  if (!apiUrl || !tenantId || !propertyId || !token) return <main className="state">Configuração necessária: informe VITE_RIBEIRA_API_URL, VITE_RIBEIRA_TENANT_ID, VITE_RIBEIRA_PROPERTY_ID e um token de sessão.</main>;
  return <Farm360Page api={new Farm360Api(apiUrl, token)} tenantId={tenantId} propertyId={propertyId} token={token} />;
}
