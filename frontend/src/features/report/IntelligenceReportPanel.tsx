import { useState } from "react";

import { Status } from "../../components/Status";
import { formatHectares } from "../../formatting";
import {
  customerAssetTypeLabel,
  customerDateLabel,
  customerSourceLabel,
} from "../../presentation";
import type {
  DigitalTwinAsset,
  FieldContext,
  PropertyDecision,
  PropertyRecord,
  Provenance,
  Scene,
} from "../../types/farm360";
import {
  decisionFieldLabel,
  decisionScopeLabel,
} from "../decisions/decisionPresentation";
import "./IntelligenceReportPanel.css";

export function IntelligenceReportPanel({
  property,
  assets,
  fields = [],
  scenes,
  provenance,
  decisions,
  open: controlledOpen,
  onOpenChange,
}: {
  property: PropertyRecord;
  assets: DigitalTwinAsset[];
  fields?: FieldContext[];
  scenes: Scene[];
  provenance: Provenance | null;
  decisions: PropertyDecision[];
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const setOpen = (next: boolean | ((current: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(open) : next;
    if (controlledOpen === undefined) setUncontrolledOpen(value);
    onOpenChange?.(value);
  };
  const area = formatHectares(property.area_hectares);
  const hasContext = scenes.length > 0 || provenance !== null;

  return <section className="report-panel"><h2>Intelligence Report V0.2</h2><p>Resumo da propriedade, dos ativos confirmados e das análises disponíveis.</p><button type="button" onClick={() => setOpen((value) => !value)}>{open ? "Fechar relatório" : "Abrir relatório"}</button>{open && <article className="intelligence-report"><header><p className="eyebrow">Ribeira Conecta · piloto beta</p><h1>Relatório de Inteligência Farm360</h1><p>Propriedade: <strong>{property.name}</strong></p></header><section><h2>Resumo executivo</h2><p>Os dados básicos da propriedade e os ativos confirmados já estão cadastrados. Análises ambientais e de sensoriamento serão enriquecidas à medida que fontes verificadas estiverem disponíveis.</p></section><section><h2>Visão da propriedade</h2><dl><dt>Área cadastrada</dt><dd>{area ? `${area} ha` : "Área ainda não disponível"}</dd><dt>Limite</dt><dd>{property.geometry_geojson ? "Disponível no mapa da propriedade" : "Ainda não disponível"}</dd><dt>Origem do limite</dt><dd>{customerSourceLabel(property.boundary_source)}</dd><dt>Confirmação</dt><dd><Status value={property.classification} /></dd></dl></section><section><h2>Ativos confirmados</h2>{assets.length === 0 ? <p>Ainda não há ativos confirmados vinculados à propriedade.</p> : <ul>{assets.map((asset) => <li key={asset.id}><strong>{asset.name}</strong> · {customerAssetTypeLabel(asset.asset_type)} · <Status value={asset.classification} />{asset.observed_at ? ` · observado em ${customerDateLabel(asset.observed_at)}` : ""}</li>)}</ul>}</section><section><h2>Contexto e dados disponíveis</h2>{hasContext ? <dl><dt>Cenas catalogadas</dt><dd>{scenes.length}</dd><dt>Fonte disponível</dt><dd>{provenance?.provider.catalog_source ?? "Contexto em atualização"}</dd><dt>Data da cena</dt><dd>{customerDateLabel(provenance?.scene?.acquisition_datetime)}</dd></dl> : <p>Contexto ambiental e de satélite ainda não disponível. Isso não altera os dados confirmados da propriedade.</p>}</section><section><h2>Riscos e recomendações</h2>{decisions.length === 0 ? <p>Ainda não há decisão persistida aplicável. A ausência de registro não confirma ausência de risco.</p> : <ul>{decisions.map((decision) => {
    const fieldLabel = decisionFieldLabel(decision, fields);
    return <li key={decision.id}><Status value={decision.classification} /> {decision.conclusion} · Escopo: {decisionScopeLabel(decision)}{fieldLabel ? ` · ${fieldLabel}` : ""}{decision.recommended_action ? ` · Próxima ação: ${String(decision.recommended_action.type ?? "revisar")}` : ""}{decision.subject_field_id && <details><summary>Contexto técnico do talhão</summary><dl><dt>Identificador</dt><dd>{decision.subject_field_id}</dd><dt>Versão do limite avaliado</dt><dd>{decision.subject_field_boundary_version ?? "Não registrada"}</dd><dt>Checksum do limite avaliado</dt><dd>{decision.subject_field_boundary_checksum ?? "Não registrado"}</dd><dt>Regra</dt><dd>{decision.rule_id && decision.rule_version !== null ? `${decision.rule_id} · versão ${decision.rule_version}` : "Não registrada"}</dd><dt>Evidências vinculadas</dt><dd>{decision.evidence_ids.length > 0 ? decision.evidence_ids.join(", ") : "Nenhuma registrada"}</dd></dl><p>O cadastro do talhão define contexto de aplicabilidade; não comprova cultivo, solo, doença ou diagnóstico agronômico.</p></details>}</li>;
  })}</ul>}</section><section><h2>Limitações atuais</h2><ul><li>Dados ausentes permanecem indisponíveis; não são preenchidos por suposição.</li><li>Metadados de catálogo não são apresentados como índice vegetal, observação agronômica ou diagnóstico.</li><li>O relatório não substitui vistoria técnica ou orientação profissional.</li></ul></section><footer><p>Emitido pela interface Farm360 em {customerDateLabel(new Date().toISOString())}.</p></footer><details><summary>Detalhes técnicos, proveniência e auditoria</summary><p>ID da propriedade: {property.id}</p><p>Classificação do limite: {property.classification}</p><p>Cenas catalogadas: {scenes.length}</p><p>Decisões persistidas: {decisions.length}</p></details><button type="button" onClick={() => window.print()}>Imprimir / salvar PDF</button></article>}</section>;
}
