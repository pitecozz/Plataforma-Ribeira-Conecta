import type { PropertyRecord } from "../../types/farm360";
import { Status } from "../../components/Status";
export function PropertyPanel({ property }: { property: PropertyRecord }) { return <section><h2>Propriedade</h2><dl><dt>Identificador</dt><dd>{property.id}</dd><dt>Nome</dt><dd>{property.name || "—"}</dd><dt>Área</dt><dd>{property.area_hectares ? `${property.area_hectares} ha` : "DADO_INSUFICIENTE"}</dd><dt>Tenant</dt><dd>{property.tenant_id}</dd><dt>Status</dt><dd><Status value={property.data_status} /></dd></dl></section>; }
