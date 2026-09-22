import type { TemporalComparison, TimelineItem } from "../../types/farm360";

interface Props {
  items: TimelineItem[];
  selectedProductId: string | null;
  mode: "view" | "compare";
  baselineProductId: string | null;
  targetProductId: string | null;
  comparison: TemporalComparison | null;
  comparisonLoading: boolean;
  onSelectProduct: (productId: string) => void;
  onModeChange: (mode: "view" | "compare") => void;
  onBaselineChange: (productId: string) => void;
  onTargetChange: (productId: string) => void;
}

function dateLabel(item: TimelineItem) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(item.acquisition_datetime));
}

export function TemporalPanel(props: Props) {
  const { items, selectedProductId, mode, baselineProductId, targetProductId, comparison, comparisonLoading } = props;
  if (items.length === 0) return <section><h2>Linha do tempo</h2><p>Sem dados disponíveis para comparação temporal.</p></section>;
  return <section className="temporal"><h2>Linha do tempo</h2><p className="temporal-order">Ordem: aquisição crescente. O padrão visual é o NDVI SUCCEEDED mais recente.</p><div className="timeline-items">{items.map(item => <button type="button" key={item.derived_product.id} className={selectedProductId === item.derived_product.id ? "selected" : ""} onClick={() => props.onSelectProduct(item.derived_product.id)}><strong>{dateLabel(item)}</strong><span>{item.derived_product.processing_status} · cobertura {item.derived_product.statistics.coverage_percentage ?? "NULL"}%</span><span>Nuvens: {item.cloud_cover ?? "UNKNOWN"}</span></button>)}</div><div className="temporal-mode"><button type="button" className={mode === "view" ? "selected" : ""} onClick={() => props.onModeChange("view")}>Visualizar</button><button type="button" className={mode === "compare" ? "selected" : ""} onClick={() => props.onModeChange("compare")}>Comparar</button></div>{mode === "compare" && <TemporalComparisonPanel items={items} baselineProductId={baselineProductId} targetProductId={targetProductId} comparison={comparison} loading={comparisonLoading} onBaselineChange={props.onBaselineChange} onTargetChange={props.onTargetChange} />}</section>;
}

function TemporalComparisonPanel({ items, baselineProductId, targetProductId, comparison, loading, onBaselineChange, onTargetChange }: Pick<Props, "items" | "baselineProductId" | "targetProductId" | "onBaselineChange" | "onTargetChange"> & { comparison: TemporalComparison | null; loading: boolean }) {
  const options = items.map(item => <option key={item.derived_product.id} value={item.derived_product.id}>{dateLabel(item)} · {item.scene_id}</option>);
  return <div className="comparison"><label>Baseline<select aria-label="Baseline" value={baselineProductId ?? ""} onChange={event => onBaselineChange(event.target.value)}>{options}</select></label><label>Target<select aria-label="Target" value={targetProductId ?? ""} onChange={event => onTargetChange(event.target.value)}>{options}</select></label>{loading && <p>Calculando comparação catalogada…</p>}{comparison && <div aria-live="polite"><h3>Comparação temporal</h3><dl><dt>Status</dt><dd>{comparison.status}</dd><dt>Delta mínimo / máximo / médio</dt><dd>{comparison.comparison.delta_minimum ?? "NULL"} / {comparison.comparison.delta_maximum ?? "NULL"} / {comparison.comparison.delta_mean ?? "NULL"}</dd><dt>Pixels comparáveis</dt><dd>{comparison.comparison.comparable_valid_pixels ?? "NULL"}</dd><dt>Cobertura comparável</dt><dd>{comparison.comparison.comparable_coverage_percentage ?? "NULL"}%</dd><dt>Alinhamento</dt><dd>{String(comparison.comparison.alignment_summary?.status ?? "NULL")}</dd></dl><p>Classificação: {comparison.comparison.classification}</p><ul>{comparison.comparison.limitations.map(limitation => <li key={limitation}>{limitation}</li>)}</ul></div>}</div>;
}
