import type { NdviProduct } from "../../types/farm360";

export function NdviPanel({ product }: { product: NdviProduct | null }) {
  if (!product) return <section><h2>NDVI</h2><p>Sem dados disponíveis para esta propriedade.</p></section>;
  const stats = product.statistics;
  return <section><h2>NDVI</h2><dl><dt>Mínimo / máximo / média</dt><dd>{stats.minimum ?? "Não disponível"} / {stats.maximum ?? "Não disponível"} / {stats.mean ?? "Não disponível"}</dd><dt>Pixels válidos</dt><dd>{stats.valid_count}</dd><dt>Cobertura</dt><dd>{stats.coverage_percentage ?? "Não disponível"}%</dd><dt>Gerado em</dt><dd>{product.generated_at}</dd><dt>Status</dt><dd>{product.processing_status}</dd></dl><details><summary>Detalhes técnicos e proveniência</summary><dl><dt>Checksum</dt><dd>{product.checksum ?? "Não disponível"}</dd><dt>Pixels sem dados</dt><dd>{stats.nodata_count}</dd><dt>Assets usados</dt><dd>{product.input_asset_keys?.join(", ") || "Não disponível"}</dd></dl></details></section>;
}
