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

  return <section className="report-panel">
    <h2>Intelligence Report V0.2</h2>
    <p>Resumo da propriedade, dos ativos confirmados e das análises disponíveis.</p>
    <button type="button" onClick={() => setOpen((value) => !value)}>{open ? "Fechar relatório" : "Abrir relatório"}</button>
    {open && <article className="intelligence-report">
      <header><p className="eyebrow">Ribeira Conecta · piloto beta</p><h1>Relatório de Inteligência Farm360</h1><p>Propriedade: <strong>{property.name}</strong></p></header>
      <section><h2>Resumo executivo</h2><p>Os dados básicos da propriedade e os ativos confirmados já estão cadastrados. Análises ambientais e de sensoriamento serão enriquecidas à medida que fontes verificadas estiverem disponíveis.</p></section>
      <section><h2>Visão da propriedade</h2><dl><dt>Área cadastrada</dt><dd>{area ? `${area} ha` : "Área ainda não disponível"}</dd><dt>Limite</dt><dd>{property.geometry_geojson ? "Disponível no mapa da propriedade" : "Ainda não disponível"}</dd><dt>Origem do limite</dt><dd>{customerSourceLabel(property.boundary_source)}</dd><dt>Confirmação</dt><dd><Status value={property.classification} /></dd></dl></section>
      <section><h2>Ativos confirmados</h2>{assets.length === 0 ? <p>Ainda não há ativos confirmados vinculados à propriedade.</p> : <ul>{assets.map((asset) => <li key={asset.id}><strong>{asset.name}</strong> · {customerAssetTypeLabel(asset.asset_type)} · <Status value={asset.classification} />{asset.observed_at ? ` · observado em ${customerDateLabel(asset.observed_at)}` : ""}</li>)}</ul>}</section>
      <section><h2>Contexto e evidências</h2>{!hasContext ? <p>Ainda não há cena de satélite ou produto derivado disponível. Isso não indica ausência de vegetação, risco ou mudança.</p> : <dl><dt>Cenas catalogadas</dt><dd>{scenes.length}</dd><dt>Produto derivado selecionado</dt><dd>{provenance ? <Status value={provenance.product.classification} /> : "Ainda não disponível"}</dd>{provenance && <><dt>Fonte</dt><dd>{provenance.provider.id} · {provenance.scene?.scene_id ?? "Cena não registrada"}</dd><dt>Limitações</dt><dd>{provenance.product.limitations.length > 0 ? provenance.product.limitations.join("; ") : "Nenhuma limitação registrada"}</dd></>}</dl>}</section>
      <section><h2>Riscos, decisões e resultados</h2>{decisions.length === 0 ? <p>Ainda não há decisão persistida aplicável a esta propriedade. A ausência de registro não confirma ausência de risco.</p> : <ul>{decisions.map((decision) => {
        const fieldLabel = decisionFieldLabel(decision, fields);
        return <li key={decision.id}>
          <Status value={decision.status} /> <Status value={decision.classification} /> · {decision.conclusion} · Escopo: {decisionScopeLabel(decision)}{fieldLabel ? ` · ${fieldLabel}` : ""}
          {decision.action && <div>
            <p>Ação: <Status value={decision.action.status} /></p>
            {decision.action.status === "COMPLETED" && <dl>
              <dt>Resultado registrado</dt><dd>{decision.action.outcome_detail ?? "Resultado não registrado"}</dd>
              <dt>Classificação do resultado</dt><dd>{decision.action.outcome_classification ? <Status value={decision.action.outcome_classification} /> : "Não registrada"}</dd>
              <dt>Concluída em</dt><dd>{decision.action.completed_at ? customerDateLabel(decision.action.completed_at) : "Não registrado"}</dd>
              <dt>Registrada por</dt><dd>{decision.action.completed_by ?? "Não registrado"}</dd>
              <dt>Evidências do resultado</dt><dd>{decision.action.outcome_evidence_ids.length > 0 ? decision.action.outcome_evidence_ids.join(", ") : "Nenhuma registrada"}</dd>
            </dl>}
          </div>}
          {decision.subject_field_id && <details><summary>Contexto técnico do talhão</summary><dl><dt>Identificador</dt><dd>{decision.subject_field_id}</dd><dt>Versão do limite avaliado</dt><dd>{decision.subject_field_boundary_version ?? "Não registrada"}</dd><dt>Checksum do limite avaliado</dt><dd>{decision.subject_field_boundary_checksum ?? "Não registrado"}</dd><dt>Limitação</dt><dd>Este resultado conserva o limite usado pela regra; alterações posteriores no cadastro não reescrevem a decisão.</dd></dl><p>O cadastro do talhão define contexto de aplicabilidade; não comprova cultivo, solo, doença ou diagnóstico agronômico.</p></details>}
        </li>;
      })}</ul>}</section>
      <details><summary>Detalhes técnicos, proveniência e auditoria</summary><p>Identificador da propriedade: {property.id}</p><p>Tenant: {property.tenant_id}</p>{provenance ? <><p>Produto: {provenance.product.id}</p><p>Cena: {provenance.scene?.scene_id ?? "Não registrada"}</p><p>Gerado em: {customerDateLabel(provenance.product.generated_at)}</p></> : <p>Nenhum produto derivado selecionado.</p>}</details>
    </article>}
  </section>;
}
