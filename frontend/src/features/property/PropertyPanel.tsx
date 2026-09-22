import type { PropertyRecord } from "../../types/farm360";
import { Status } from "../../components/Status";
import { formatHectares } from "../../formatting";
import { customerSourceLabel } from "../../presentation";

export function PropertyPanel({ property }: { property: PropertyRecord }) {
  const area = formatHectares(property.area_hectares);
  return <section><h2>Visão da propriedade</h2><dl><dt>Nome</dt><dd>{property.name || "—"}</dd><dt>Área cadastrada</dt><dd>{area ? `${area} ha` : "Área ainda não disponível"}</dd><dt>Limite</dt><dd>{property.geometry_geojson ? "Disponível no mapa" : "Ainda não disponível"}</dd><dt>Origem do limite</dt><dd>{customerSourceLabel(property.boundary_source)}</dd><dt>Confirmação</dt><dd><Status value={property.classification} /></dd><dt>Status das análises</dt><dd><Status value={property.data_status} /></dd></dl><details><summary>Detalhes técnicos e proveniência</summary><dl><dt>Identificador da propriedade</dt><dd>{property.id}</dd><dt>Identificador do tenant</dt><dd>{property.tenant_id}</dd><dt>CRS</dt><dd>{property.geometry_crs ?? "Não informado"}</dd><dt>Checksum do limite</dt><dd>{property.boundary_checksum ?? "Não disponível"}</dd><dt>Origem técnica</dt><dd>{property.boundary_source ?? "Não informada"}</dd><dt>Classificação técnica</dt><dd>{property.classification}</dd><dt>Criada em</dt><dd>{property.created_at}</dd><dt>Atualizada em</dt><dd>{property.updated_at ?? "Não informado"}</dd></dl></details></section>;
}
