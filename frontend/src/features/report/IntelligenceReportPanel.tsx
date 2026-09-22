import { useState } from "react";

import type {
  DigitalTwinAsset,
  PropertyDecision,
  PropertyRecord,
  Provenance,
  Scene,
} from "../../types/farm360";
import { Status } from "../../components/Status";
import { formatHectares } from "../../formatting";
import {
  customerAssetTypeLabel,
  customerDateLabel,
  customerSourceLabel,
} from "../../presentation";
import "./IntelligenceReportPanel.css";

export function IntelligenceReportPanel({
  property,
  assets,
  scenes,
  provenance,
  decisions,
}: {
  property: PropertyRecord;
  assets: DigitalTwinAsset[];
  scenes: Scene[];
  provenance: Provenance | null;
  decisions: PropertyDecision[];
}) {
  const [open, setOpen] = useState(false);
  const area = formatHectares(property.area_hectares);
  const hasContext = scenes.length > 0 || provenance !== null;
  return <section className="report-panel"><h2>Intelligence Report V0.2</h2><p>Resumo da propriedade, dos ativos confirmados e das análises disponíveis.</p><button type="button" onClick={() => setOpen((value) => !value)}>{open ? "Fechar relatório" : "Abrir relatório"}</button>{open && <article className="intelligence-report"><header><p className="eyebrow">Ribeira Conecta · piloto beta</p><h1>Relatório de Inteligência Farm360</h1><p>Propriedade: <strong>{property.name}</strong></p></header><section><h2>Resumo executivo</h2><p>Os dados básicos da propriedade e os ativos confirmados já estão cadastrados. Análises ambientais e de sensoriamento serão enriquecidas à medida que fontes verificadas estiverem disponíveis.</p></section><section><h2>Visão da propriedade</h2><dl><dt>Área cadastrada</dt><dd>{area ? `${area} ha` : "Área ainda não disponível"}</dd><dt>Limite</dt><dd>{property.geometry_geojson ? "Disponível no mapa da propriedade" : "Ainda não disponível"}</dd><dt>Origem do limite</dt><dd>{customerSourceLabel(property.boundary_source)}</dd><dt>Confirmação</dt><dd><Status value={property.classification} /></dd></dl></section><section><h2>Ativos confirmados</h2>{assets.length === 0 ? <p>Ainda não há ativos confirmados vinculados à propriedade.</p> : <ul>{assets.map((asset) => <li key={asset.id}><strong>{asset.name}</strong> · {customerAssetTypeLabel(asset.asset_type)} · <Status value={asset.classification} />{asset.observed_at ? ` · observado em ${customerDateLabel(asset.observed_at)}` : ""}</li>)}</ul>}</section><section><h2>Contexto e dados disponíveis</h2>{hasContext ? <dl><dt>Cenas catalogadas</dt><dd>{scenes.length}</dd><dt>Fonte disponível</dt><dd>{provenance?.provider.catalog_source ?? "Contexto em atualização"}</dd><dt>Data da cena</dt><dd>{customerDateLabel(provenance?.scene?.acquisition_datetime)}</dd></dl> : <p>Contexto ambiental e de sensoriamento ainda não está disponível para esta propriedade. Isso não altera os limites e ativos já confirmados.</p>}</section><section><h2>Riscos, decisões e recomendações</h2>{decisions.length === 0 ? <p>Ainda não há risco, decisão ou recomendação persistida aplicável a esta propriedade. A ausência de registro não confirma ausência de risco.</p> : <ul>{decisions.map((decision) => <li key={decision.id}>{decision.conclusion}</li>)}</ul>}<p>Oportunidades comerciais dependem de evidência, necessidade identificada e serviço aplicável.</p></section><section><h2>Próximos passos de validação</h2><p>Quando houver novas fontes verificadas, elas poderão complementar o contexto ambiental e de sensoriamento. Nenhuma análise agronômica, legal ou de perdas é inferida enquanto os dados necessários não estiverem disponíveis.</p></section><section><h2>Fontes e limitações</h2><p>Este relatório separa informação confirmada de contexto ainda indisponível. Camadas remotas ou derivadas não substituem observação de campo, laboratório, laudo ou validação legal.</p></section><details><summary>Detalhes técnicos, proveniência e auditoria</summary><dl><dt>Identificador da propriedade</dt><dd>{property.id}</dd><dt>Checksum do limite</dt><dd>{property.boundary_checksum ?? "Não disponível"}</dd><dt>Fonte técnica do limite</dt><dd>{property.boundary_source ?? "Não informada"}</dd><dt>Produto técnico</dt><dd>{provenance?.product.product_type ?? "Não disponível"}</dd><dt>Checksum do produto</dt><dd>{provenance?.product.checksum ?? "Não disponível"}</dd><dt>Algoritmo</dt><dd>{provenance ? `${provenance.product.algorithm_id} ${provenance.product.algorithm_version}` : "Não disponível"}</dd></dl></details><button type="button" onClick={() => window.print()}>Imprimir / salvar PDF</button></article>}</section>;
}
