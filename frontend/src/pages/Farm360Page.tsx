import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Farm360Api } from "../api/client";
import type {
  DigitalTwinAsset,
  NdviProduct,
  PropertyRecord,
  PropertyDecision,
  Provenance,
  Scene,
  TemporalComparison,
  TimelineItem,
} from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { LayerManager } from "../features/map/LayerManager";
import { AssetPanel } from "../features/assets/AssetPanel";
import { IntelligenceReportPanel } from "../features/report/IntelligenceReportPanel";
import { PilotFeedbackPanel } from "../features/feedback/PilotFeedbackPanel";
import { RiskDecisionPanel } from "../features/decisions/RiskDecisionPanel";
import { canRenderNdvi } from "../features/map/layerState";
import { PropertyPanel } from "../features/property/PropertyPanel";
import { SatellitePanel } from "../features/satellite/SatellitePanel";
import { NdviPanel } from "../features/ndvi/NdviPanel";
import { ProvenancePanel } from "../features/provenance/ProvenancePanel";
import { TemporalPanel } from "../features/temporal/TemporalPanel";
import { SceneOperationsPanel } from "../features/operations/SceneOperationsPanel";
import { BoundaryImportPanel } from "../features/property/BoundaryImportPanel";
import { BoundaryEditorPanel } from "../features/property/BoundaryEditorPanel";
import { DataAvailabilityPanel } from "../features/context/DataAvailabilityPanel";
import { formatHectares } from "../formatting";

interface Props {
  api: Farm360Api;
  apiBaseUrl: string;
  tenantId: string;
  propertyId: string;
  token: string;
  canManageBoundary?: boolean;
  canRunSatelliteOperations?: boolean;
}
type LoadState = "loading" | "ready" | "empty" | "error";
type PartialLoadIssues = {
  assets: boolean;
  context: boolean;
  decisions: boolean;
  provenance: boolean;
};

const noPartialLoadIssues: PartialLoadIssues = {
  assets: false,
  context: false,
  decisions: false,
  provenance: false,
};

function newestSucceeded(items: TimelineItem[]) {
  return (
    [...items]
      .reverse()
      .find((item) => item.derived_product.processing_status === "SUCCEEDED") ??
    null
  );
}

export function Farm360Page({
  api,
  apiBaseUrl,
  tenantId,
  propertyId,
  token,
  canManageBoundary = false,
  canRunSatelliteOperations = false,
}: Props) {
  const [state, setState] = useState<LoadState>("loading");
  const [property, setProperty] = useState<PropertyRecord | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [assets, setAssets] = useState<DigitalTwinAsset[]>([]);
  const [decisions, setDecisions] = useState<PropertyDecision[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(
    null,
  );
  const [provenanceProductId, setProvenanceProductId] = useState<string | null>(
    null,
  );
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [ndviEnabled, setNdviEnabled] = useState(false);
  const [deltaEnabled, setDeltaEnabled] = useState(false);
  const [mode, setMode] = useState<"view" | "compare">("view");
  const [baselineProductId, setBaselineProductId] = useState<string | null>(
    null,
  );
  const [targetProductId, setTargetProductId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<TemporalComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [partialLoadIssues, setPartialLoadIssues] =
    useState<PartialLoadIssues>(noPartialLoadIssues);
  const [optionalDataLoading, setOptionalDataLoading] = useState(true);
  const [recenterRequest, setRecenterRequest] = useState(0);
  const [reportOpen, setReportOpen] = useState(false);
  const assetPanelAnchor = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    setState("loading");
    setOptionalDataLoading(true);
    setPartialLoadIssues(noPartialLoadIssues);
    try {
      const propertyResult = await api.property(tenantId, propertyId);
      setProperty(propertyResult);
      setState("ready");
      const [scenesResult, timelineResult, assetsResult, decisionsResult] =
        await Promise.allSettled([
          api.scenes(tenantId, propertyId),
          api.timeline(tenantId, propertyId),
          api.assets(tenantId, propertyId),
          api.decisions(tenantId, propertyId),
        ]);
      const scenesItems = scenesResult.status === "fulfilled" ? scenesResult.value.items : [];
      const timelineItems = timelineResult.status === "fulfilled" ? timelineResult.value.items : [];
      const assetItems = assetsResult.status === "fulfilled" ? assetsResult.value.items : [];
      const decisionItems = decisionsResult.status === "fulfilled" ? decisionsResult.value.items : [];
      const selected = newestSucceeded(timelineItems);
      const provenanceResult = selected
        ? await api.provenance(tenantId, selected.derived_product.id).catch(() => null)
        : null;
      setScenes(scenesItems);
      setAssets(assetItems);
      setDecisions(decisionItems);
      setSelectedAssetId((current) =>
        current && assetItems.some((asset) => asset.id === current)
          ? current
          : null,
      );
      setTimeline(timelineItems);
      setSelectedProductId(selected?.derived_product.id ?? null);
      setProvenanceProductId(selected?.derived_product.id ?? null);
      setBaselineProductId(timelineItems[0]?.derived_product.id ?? null);
      setTargetProductId(
        selected?.derived_product.id ??
          timelineItems.at(-1)?.derived_product.id ??
          null,
      );
      setProvenance(provenanceResult);
      setPartialLoadIssues({
        assets: assetsResult.status === "rejected",
        context: scenesResult.status === "rejected" || timelineResult.status === "rejected",
        decisions: decisionsResult.status === "rejected",
        provenance: Boolean(selected) && provenanceResult === null,
      });
    } catch {
      setState("error");
    } finally {
      setOptionalDataLoading(false);
    }
  }, [api, propertyId, tenantId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selected =
    timeline.find((item) => item.derived_product.id === selectedProductId) ??
    null;
  const product: NdviProduct | null = selected?.derived_product ?? null;
  const scene = selected
    ? (scenes.find(
        (candidate) => candidate.id === selected.scene_internal_id,
      ) ?? null)
    : null;
  const tileUrl = useMemo(
    () =>
      product && canRenderNdvi(product, ndviEnabled)
        ? api.tileTemplate(tenantId, product.id)
        : null,
    [api, ndviEnabled, product, tenantId],
  );
  const deltaTileUrl = useMemo(
    () =>
      comparison?.comparison.delta_product_id && deltaEnabled
        ? api.tileTemplate(tenantId, comparison.comparison.delta_product_id)
        : null,
    [api, comparison, deltaEnabled, tenantId],
  );

  useEffect(() => {
    let active = true;
    if (!provenanceProductId) {
      setProvenance(null);
      return () => {
        active = false;
      };
    }
    void api
      .provenance(tenantId, provenanceProductId)
      .then((result) => {
        if (active) setProvenance(result);
      })
      .catch(() => {
        if (active) setProvenance(null);
      });
    return () => {
      active = false;
    };
  }, [api, provenanceProductId, tenantId]);

  useEffect(() => {
    let active = true;
    if (mode !== "compare" || !baselineProductId || !targetProductId) {
      setComparison(null);
      return () => {
        active = false;
      };
    }
    setComparisonLoading(true);
    void api
      .comparison(tenantId, propertyId, baselineProductId, targetProductId)
      .then((result) => {
        if (active) setComparison(result);
      })
      .catch(() => {
        if (active) setComparison(null);
      })
      .finally(() => {
        if (active) setComparisonLoading(false);
      });
    return () => {
      active = false;
    };
  }, [api, baselineProductId, mode, propertyId, targetProductId, tenantId]);

  if (state === "loading")
    return <main className="state">Carregando Farm 360…</main>;
  if (state === "error")
    return (
      <main className="state">
        Não foi possível atualizar os dados da propriedade agora.
      </main>
    );
  if (!property)
    return (
      <main className="state">
        Os dados básicos desta propriedade ainda não estão disponíveis.
      </main>
    );

  const area = formatHectares(property.area_hectares);
  const showAssets = () => {
    assetPanelAnchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (assets[0]) setSelectedAssetId(assets[0].id);
  };

  return (
    <main className="farm360">
      <div className="map-column">
        <MapCanvas
          aoi={property.geometry_geojson}
          assets={assets}
          selectedAssetId={selectedAssetId}
          onAssetSelected={setSelectedAssetId}
          apiBaseUrl={apiBaseUrl}
          tileUrl={tileUrl}
          deltaTileUrl={deltaTileUrl}
          ndviEnabled={ndviEnabled}
          deltaEnabled={deltaEnabled}
          token={token}
          recenterRequest={recenterRequest}
        />
        <div className="map-tools">
          {product ? <label><input type="checkbox" checked={ndviEnabled} onChange={(event) => setNdviEnabled(event.target.checked)} /> NDVI</label> : <span>NDVI: sem dados disponíveis</span>}
          {comparison?.comparison.delta_product_id ? <label><input type="checkbox" checked={deltaEnabled} onChange={(event) => setDeltaEnabled(event.target.checked)} /> Δ NDVI</label> : <span>Comparação NDVI: sem dados disponíveis</span>}
          {comparison?.comparison.delta_product_id && (
            <button
              type="button"
              onClick={() =>
                setProvenanceProductId(comparison.comparison.delta_product_id)
              }
            >
              Proveniência do Δ NDVI
            </button>
          )}
          <span className="legend">
            <i /> −1 solo/água <b /> +1 vegetação
          </span>
          {comparison?.comparison.delta_product_id && (
            <span className="delta-legend">
              vermelho: NDVI menor no target · branco: próximo de zero · azul:
              NDVI maior no target
            </span>
          )}
        </div>
      </div>
      <aside>
        <section className="property-summary">
          <p className="eyebrow">Farm360</p>
          <h1>{property.name}</h1>
          <p className="property-summary-facts">
            {area ? `${area} ha` : "Área ainda não disponível"} · {assets.length} ativo(s) confirmado(s)
          </p>
          <dl>
            <dt>Limite</dt><dd>{property.geometry_geojson ? "Disponível e visível no mapa" : "Ainda não disponível"}</dd>
            <dt>Contexto ambiental</dt><dd>Em enriquecimento</dd>
            <dt>Satélite</dt><dd>{scenes.length > 0 ? "Cenas catalogadas" : "Aguardando dados"}</dd>
          </dl>
          <div className="property-summary-actions">
            <button type="button" onClick={() => setRecenterRequest((value) => value + 1)}>Centralizar propriedade</button>
            <button type="button" onClick={showAssets}>Ver ativos</button>
            <button type="button" onClick={() => setReportOpen(true)}>Abrir relatório</button>
          </div>
        </section>
        <section className="context-availability">
          <h2>Contexto e evidências</h2>
          {optionalDataLoading ? <p>Carregando contexto disponível…</p> : partialLoadIssues.context || partialLoadIssues.provenance ? <p>Não foi possível atualizar parte do contexto agora. Propriedade, limite e ativos disponíveis continuam acessíveis.</p> : scenes.length === 0 && timeline.length === 0 ? <p>Contexto ainda não disponível. Isso não altera os dados confirmados da propriedade.</p> : <p>Contexto persistido disponível para consulta.</p>}
        </section>
        <LayerManager ndviAvailable={Boolean(product && product.processing_status === "SUCCEEDED")} ndviEnabled={ndviEnabled} onNdviEnabled={setNdviEnabled} deltaAvailable={Boolean(comparison?.comparison.delta_product_id)} deltaEnabled={deltaEnabled} onDeltaEnabled={setDeltaEnabled} />
        <DataAvailabilityPanel property={property} assets={assets} scenes={scenes} timeline={timeline} />
        <IntelligenceReportPanel property={property} assets={assets} scenes={scenes} provenance={provenance} decisions={decisions} open={reportOpen} onOpenChange={setReportOpen} />
        <PilotFeedbackPanel api={api} tenantId={tenantId} propertyId={propertyId} />
        {partialLoadIssues.decisions && <section><h2>Riscos e decisões</h2><p>Não foi possível atualizar decisões agora. Isso não confirma ausência de risco ou oportunidade.</p></section>}
        {!partialLoadIssues.decisions && <RiskDecisionPanel decisions={decisions} />}
        <div ref={assetPanelAnchor}>
          <AssetPanel
            assets={assets}
            selectedAssetId={selectedAssetId}
            onSelect={setSelectedAssetId}
            loadError={partialLoadIssues.assets}
          />
        </div>
        {canRunSatelliteOperations && <SceneOperationsPanel
          api={api}
          tenantId={tenantId}
          propertyId={propertyId}
          scenes={scenes}
          onChanged={refresh}
        />}
        {canManageBoundary && <BoundaryImportPanel
          api={api}
          tenantId={tenantId}
          property={property}
          onBoundaryChanged={refresh}
        />}
        {canManageBoundary && <BoundaryEditorPanel
          api={api}
          tenantId={tenantId}
          property={property}
          onChanged={refresh}
        />}
        <TemporalPanel
          items={timeline}
          selectedProductId={selectedProductId}
          mode={mode}
          baselineProductId={baselineProductId}
          targetProductId={targetProductId}
          comparison={comparison}
          comparisonLoading={comparisonLoading}
          onSelectProduct={(productId) => {
            setSelectedProductId(productId);
            setProvenanceProductId(productId);
          }}
          onModeChange={setMode}
          onBaselineChange={setBaselineProductId}
          onTargetChange={setTargetProductId}
        />
        <PropertyPanel property={property} />
        <SatellitePanel scene={scene} scenes={scenes} />
        <NdviPanel product={product} />
        <ProvenancePanel provenance={provenance} />
      </aside>
    </main>
  );
}
