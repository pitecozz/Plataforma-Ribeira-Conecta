import { useState } from "react";

import type { DigitalTwinAsset, PropertyRecord, Provenance, Scene } from "../../types/farm360";
import { Status } from "../../components/Status";
import "./IntelligenceReportPanel.css";

export function IntelligenceReportPanel({
  property,
  assets,
  scenes,
  provenance,
}: {
  property: PropertyRecord;
  assets: DigitalTwinAsset[];
  scenes: Scene[];
  provenance: Provenance | null;
}) {
  const [open, setOpen] = useState(false);
  return <section className="report-panel"><h2>Intelligence Report V0.1</h2><p>Relatório HTML com dados persistidos disponíveis e limitações explícitas.</p><button type="button" onClick={() => setOpen((value) => !value)}>{open ? "Fechar relatório" : "Abrir relatório"}</button>{open && <article className="intelligence-report"><header><p className="eyebrow">Ribeira Conecta · beta</p><h1>Farm360 Intelligence Report</h1><p>Propriedade: <strong>{property.name}</strong></p></header><section><h2>Resumo executivo</h2><p>Este relatório apresenta somente contexto disponível para a propriedade. Não constitui diagnóstico agronômico, laudo, análise legal, estimativa de perdas ou garantia operacional.</p></section><section><h2>Propriedade e limite</h2><dl><dt>Status de dados</dt><dd><Status value={property.data_status} /></dd><dt>Área</dt><dd>{property.area_hectares ?? "UNKNOWN"} ha</dd><dt>Fonte do limite</dt><dd>{property.boundary_source ?? "UNKNOWN"}</dd><dt>Classificação</dt><dd><Status value={property.classification} /></dd></dl></section><section><h2>Ativos confirmados</h2>{assets.length === 0 ? <p>DADO_INSUFICIENTE — nenhum ativo confirmado vinculado à propriedade.</p> : <ul>{assets.map((asset) => <li key={asset.id}>{asset.name} · {asset.asset_type} · <Status value={asset.classification} /> · fonte {asset.source_reference ?? "UNKNOWN"} · observado {asset.observed_at ?? "UNKNOWN"}</li>)}</ul>}</section><section><h2>Contexto ambiental e sensoriamento</h2><dl><dt>Cenas catalogadas</dt><dd>{scenes.length}</dd><dt>Produto com proveniência</dt><dd>{provenance?.product.product_type ?? "UNKNOWN"}</dd><dt>Fonte/provedor</dt><dd>{provenance?.provider.catalog_source ?? "UNKNOWN"}</dd><dt>Data da cena</dt><dd>{provenance?.scene?.acquisition_datetime ?? "UNKNOWN"}</dd></dl></section><section><h2>Riscos, oportunidades e recomendações</h2><p>UNKNOWN — esta versão beta ainda não apresenta um resumo customer-facing de regras, decisões ou oportunidades. Nenhum risco, necessidade comercial ou recomendação é criado por ausência dessa tela.</p></section><section><h2>Fontes e limitações</h2><p>Use a visualização de proveniência do Farm360 para evidências de cena/produto. Camadas remotas/derivadas não são observações de campo ou laboratório. Dados faltantes permanecem `UNKNOWN`, `DADO_INSUFICIENTE` ou `INCONCLUSIVE`.</p></section><button type="button" onClick={() => window.print()}>Imprimir / salvar PDF</button></article>}</section>;
}
