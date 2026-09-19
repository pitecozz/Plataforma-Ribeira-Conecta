import type { PropertyRecord } from "../../types/farm360";
import { Status } from "../../components/Status";

export function PropertyPanel({ property }: { property: PropertyRecord }) {
  return <section><h2>Propriedade</h2><dl><dt>Identificador</dt><dd>{property.id}</dd><dt>Nome</dt><dd>{property.name || "—"}</dd><dt>Área calculada</dt><dd>{property.area_hectares ? `${property.area_hectares} ha` : "DADO_INSUFICIENTE"}</dd><dt>CRS</dt><dd>{property.geometry_crs ?? "UNKNOWN"}</dd><dt>Origem do limite</dt><dd>{property.boundary_source ?? "UNKNOWN"}</dd><dt>Checksum do limite</dt><dd>{property.boundary_checksum ?? "UNKNOWN"}</dd><dt>Classificação</dt><dd><Status value={property.classification} /></dd><dt>Criada em</dt><dd>{property.created_at}</dd><dt>Atualizada em</dt><dd>{property.updated_at ?? "UNKNOWN"}</dd><dt>Tenant</dt><dd>{property.tenant_id}</dd><dt>Status</dt><dd><Status value={property.data_status} /></dd></dl></section>;
}
