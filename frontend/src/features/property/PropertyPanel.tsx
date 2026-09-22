import type { PropertyRecord } from "../../types/farm360";
import { Status } from "../../components/Status";
import { formatHectares } from "../../formatting";

export function PropertyPanel({ property }: { property: PropertyRecord }) {
  const area = formatHectares(property.area_hectares);
  return <section><h2>Propriedade</h2><dl><dt>Identificador</dt><dd>{property.id}</dd><dt>Nome</dt><dd>{property.name || "—"}</dd><dt>Área calculada</dt><dd>{area ? `${area} ha` : "Área ainda não disponível"}</dd><dt>CRS</dt><dd>{property.geometry_crs ?? "Não informado"}</dd><dt>Origem do limite</dt><dd>{property.boundary_source ?? "Não informada"}</dd><dt>Checksum do limite</dt><dd>{property.boundary_checksum ?? "Não disponível"}</dd><dt>Classificação</dt><dd><Status value={property.classification} /></dd><dt>Criada em</dt><dd>{property.created_at}</dd><dt>Atualizada em</dt><dd>{property.updated_at ?? "Não informado"}</dd><dt>Tenant</dt><dd>{property.tenant_id}</dd><dt>Status</dt><dd><Status value={property.data_status} /></dd></dl></section>;
}
