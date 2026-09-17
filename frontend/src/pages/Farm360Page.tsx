import { useEffect, useMemo, useState } from "react";
import type { Farm360Api } from "../api/client";
import type { NdviProduct, PropertyRecord, Provenance, Scene, TemporalComparison, TimelineItem } from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { canRenderNdvi } from "../features/map/layerState";
import { PropertyPanel } from "../features/property/PropertyPanel";
import { SatellitePanel } from "../features/satellite/SatellitePanel";
import { NdviPanel } from "../features/ndvi/NdviPanel";
import { ProvenancePanel } from "../features/provenance/ProvenancePanel";
import { TemporalPanel } from "../features/temporal/TemporalPanel";

interface Props { api: Farm360Api; apiBaseUrl: string; tenantId: string; propertyId: string; token: string; }
type LoadState = "loading" | "ready" | "empty" | "error";

function newestSucceeded(items: TimelineItem[]) {
  return [...items].reverse().find(item => item.derived_product.processing_status === "SUCCEEDED") ?? null;
}

export function Farm360Page({ api, apiBaseUrl, tenantId, propertyId, token }: Props) {
  const [state, setState] = useState<LoadState>("loading");
  const [property, setProperty] = useState<PropertyRecord | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [ndviEnabled, setNdviEnabled] = useState(true);
  const [mode, setMode] = useState<"view" | "compare">("view");
  const [baselineProductId, setBaselineProductId] = useState<string | null>(null);
  const [targetProductId, setTargetProductId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<TemporalComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setState("loading");
      try {
        const [propertyResult, scenesResult, timelineResult] = await Promise.all([api.property(tenantId, propertyId), api.scenes(tenantId, propertyId), api.timeline(tenantId, propertyId)]);
        const selected = newestSucceeded(timelineResult.items);
        const provenanceResult = selected ? await api.provenance(tenantId, selected.derived_product.id) : null;
        if (!active) return;
        setProperty(propertyResult);
        setScenes(scenesResult.items);
        setTimeline(timelineResult.items);
        setSelectedProductId(selected?.derived_product.id ?? null);
        setBaselineProductId(timelineResult.items[0]?.derived_product.id ?? null);
        setTargetProductId(selected?.derived_product.id ?? timelineResult.items.at(-1)?.derived_product.id ?? null);
        setProvenance(provenanceResult);
        setState(selected || scenesResult.items.length > 0 ? "ready" : "empty");
      } catch { if (active) setState("error"); }
    };
    void load();
    return () => { active = false; };
  }, [api, propertyId, tenantId]);

  const selected = timeline.find(item => item.derived_product.id === selectedProductId) ?? null;
  const product: NdviProduct | null = selected?.derived_product ?? null;
  const scene = selected ? scenes.find(candidate => candidate.id === selected.scene_internal_id) ?? null : null;
  const tileUrl = useMemo(() => product && canRenderNdvi(product, ndviEnabled) ? api.tileTemplate(tenantId, product.id) : null, [api, ndviEnabled, product, tenantId]);

  useEffect(() => {
    let active = true;
    if (!selectedProductId) { setProvenance(null); return () => { active = false; }; }
    void api.provenance(tenantId, selectedProductId).then(result => { if (active) setProvenance(result); }).catch(() => { if (active) setProvenance(null); });
    return () => { active = false; };
  }, [api, selectedProductId, tenantId]);

  useEffect(() => {
    let active = true;
    if (mode !== "compare" || !baselineProductId || !targetProductId) { setComparison(null); return () => { active = false; }; }
    setComparisonLoading(true);
    void api.comparison(tenantId, propertyId, baselineProductId, targetProductId)
      .then(result => { if (active) setComparison(result); })
      .catch(() => { if (active) setComparison(null); })
      .finally(() => { if (active) setComparisonLoading(false); });
    return () => { active = false; };
  }, [api, baselineProductId, mode, propertyId, targetProductId, tenantId]);

  if (state === "loading") return <main className="state">Carregando Farm 360…</main>;
  if (state === "error") return <main className="state">SOURCE_UNAVAILABLE — não foi possível carregar os dados persistidos.</main>;
  if (!property || state === "empty") return <main className="state">DADO_INSUFICIENTE — esta propriedade não possui cena ou NDVI persistido.</main>;

  return <main className="farm360"><div className="map-column"><MapCanvas aoi={property.geometry_geojson} apiBaseUrl={apiBaseUrl} tileUrl={tileUrl} ndviEnabled={ndviEnabled} token={token} /><div className="map-tools"><label><input type="checkbox" checked={ndviEnabled} onChange={event => setNdviEnabled(event.target.checked)} disabled={!product} /> NDVI</label><span className="legend"><i /> −1 solo/água <b /> +1 vegetação</span>{!product && <span>Nodata: transparente</span>}</div></div><aside><TemporalPanel items={timeline} selectedProductId={selectedProductId} mode={mode} baselineProductId={baselineProductId} targetProductId={targetProductId} comparison={comparison} comparisonLoading={comparisonLoading} onSelectProduct={setSelectedProductId} onModeChange={setMode} onBaselineChange={setBaselineProductId} onTargetChange={setTargetProductId} /><PropertyPanel property={property} /><SatellitePanel scene={scene} /><NdviPanel product={product} /><ProvenancePanel provenance={provenance} /></aside></main>;
}
