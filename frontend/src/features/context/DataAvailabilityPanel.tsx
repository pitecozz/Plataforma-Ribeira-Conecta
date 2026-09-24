import type { DigitalTwinAsset, FieldContext, PropertyRecord, Scene, TimelineItem } from "../../types/farm360";
import "./DataAvailabilityPanel.css";

type Availability = "available" | "partial" | "awaiting" | "not-configured";

type AvailabilityItem = {
  label: string;
  state: Availability;
  detail: string;
};

const stateLabel: Record<Availability, string> = {
  available: "Disponível",
  partial: "Parcial",
  awaiting: "Aguardando dados",
  "not-configured": "Não configurado",
};

export function DataAvailabilityPanel({
  property,
  assets,
  fields,
  scenes,
  timeline,
  fieldsUnavailable = false,
}: {
  property: PropertyRecord;
  assets: DigitalTwinAsset[];
  fields: FieldContext[];
  scenes: Scene[];
  timeline: TimelineItem[];
  fieldsUnavailable?: boolean;
}) {
  const hasDerivedProduct = timeline.some(
    (item) => item.derived_product.processing_status === "SUCCEEDED",
  );
  const items: AvailabilityItem[] = [
    {
      label: "Limite da propriedade",
      state: property.geometry_geojson ? "available" : "awaiting",
      detail: property.geometry_geojson
        ? "Limite cadastrado e visível no mapa"
        : "Nenhum limite cadastrado",
    },
    {
      label: "Ativos",
      state: assets.length > 0 ? "available" : "awaiting",
      detail: assets.length > 0 ? `${assets.length} ativo(s) confirmado(s)` : "Nenhum ativo confirmado",
    },
    {
      label: "Talhões operacionais",
      state: fieldsUnavailable ? "partial" : fields.length > 0 ? "available" : "awaiting",
      detail: fieldsUnavailable
        ? "Inventário de talhões indisponível nesta consulta"
        : fields.length > 0
          ? `${fields.length} talhão(ões) com fonte e tempo registrados`
          : "Nenhum talhão operacional registrado",
    },
    {
      label: "Satélite",
      state: hasDerivedProduct ? "available" : scenes.length > 0 ? "partial" : "awaiting",
      detail: hasDerivedProduct
        ? "Produto processado disponível"
        : scenes.length > 0
          ? "Cenas catalogadas; sem produto disponível"
          : "Nenhuma cena ou produto disponível",
    },
    { label: "Ambiente e clima", state: "awaiting", detail: "Ainda sem fonte persistida" },
    { label: "Água e inundação", state: "awaiting", detail: "Ainda sem avaliação aplicável" },
    { label: "Solo e laboratório", state: "not-configured", detail: "Nenhuma coleta ou análise vinculada" },
    { label: "IoT e sensores", state: "not-configured", detail: "Nenhum dispositivo vinculado" },
    { label: "Energia", state: "not-configured", detail: "Nenhuma medição vinculada" },
  ];

  return (
    <section className="data-availability">
      <h2>Disponibilidade de dados</h2>
      <p>Mostra o que já está registrado para esta propriedade, sem estimar o que ainda não foi coletado.</p>
      <ul>
        {items.map((item) => (
          <li key={item.label}>
            <div><strong>{item.label}</strong><small>{item.detail}</small></div>
            <span className={`availability-state ${item.state}`}>{stateLabel[item.state]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
