import { useEffect, useMemo, useState } from "react";
import type { Farm360Api } from "../api/client";
import type { NdviProduct, PropertyRecord, Provenance, Scene } from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { canRenderNdvi } from "../features/map/layerState";
import { PropertyPanel } from "../features/property/PropertyPanel";
import { SatellitePanel } from "../features/satellite/SatellitePanel";
import { NdviPanel } from "../features/ndvi/NdviPanel";
import { ProvenancePanel } from "../features/provenance/ProvenancePanel";

interface Props { api: Farm360Api; tenantId: string; propertyId: string; token: string; }
type LoadState = "loading" | "ready" | "empty" | "error";

export function Farm360Page({ api, tenantId, propertyId, token }: Props) {
  const [state, setState] = useState<LoadState>("loading");
  const [property, setProperty] = useState<PropertyRecord | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [products, setProducts] = useState<NdviProduct[]>([]);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [ndviEnabled, setNdviEnabled] = useState(true);
  useEffect(() => {
    let active = true;
    const load = async () => {
      setState("loading");
      try {
        const [propertyResult, scenesResult, productsResult] = await Promise.all([api.property(tenantId, propertyId), api.scenes(tenantId, propertyId), api.products(tenantId, propertyId)]);
        const selected = productsResult.items.find(product => product.processing_status === "SUCCEEDED") ?? null;
        const provenanceResult = selected ? await api.provenance(tenantId, selected.id) : null;
        if (!active) return;
        setProperty(propertyResult); setScenes(scenesResult.items); setProducts(productsResult.items); setProvenance(provenanceResult);
        setState(selected || scenesResult.items.length > 0 ? "ready" : "empty");
      } catch { if (active) setState("error"); }
    };
    void load(); return () => { active = false; };
  }, [api, propertyId, tenantId]);
  const product = products.find(candidate => candidate.processing_status === "SUCCEEDED") ?? null;
  const tileUrl = useMemo(() => product && canRenderNdvi(product, ndviEnabled) ? api.tileTemplate(tenantId, product.id) : null, [api, ndviEnabled, product, tenantId]);
  if (state === "loading") return <main className="state">Carregando Farm 360…</main>;
  if (state === "error") return <main className="state">SOURCE_UNAVAILABLE — não foi possível carregar os dados persistidos.</main>;
  if (!property || state === "empty") return <main className="state">DADO_INSUFICIENTE — esta propriedade não possui cena ou NDVI persistido.</main>;
  return <main className="farm360"><div className="map-column"><MapCanvas aoi={property.geometry_geojson} tileUrl={tileUrl} ndviEnabled={ndviEnabled} token={token} /><div className="map-tools"><label><input type="checkbox" checked={ndviEnabled} onChange={event => setNdviEnabled(event.target.checked)} disabled={!product} /> NDVI</label><span className="legend"><i /> −1 solo/água <b /> +1 vegetação</span>{!product && <span>Nodata: transparente</span>}</div></div><aside><PropertyPanel property={property} /><SatellitePanel scene={scenes[0] ?? null} /><NdviPanel product={product} /><ProvenancePanel provenance={provenance} /></aside></main>;
}
