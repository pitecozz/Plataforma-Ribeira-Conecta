import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { Geometry } from "geojson";
import type { Farm360Api } from "../api/client";
import type { PropertyCreate, PortfolioProperty } from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { formatHectares } from "../formatting";
import { customerPropertyName } from "../presentation";
import { Farm360Page } from "./Farm360Page";
import "./PropertyWorkspace.css";

export function PropertyWorkspace({ api, apiBaseUrl, tenantId, token, initialPropertyId, canManageProperties = false, canManageBoundary = false, canRunSatelliteOperations = false }: { api: Farm360Api; apiBaseUrl: string; tenantId: string; token: string; initialPropertyId?: string; canManageProperties?: boolean; canManageBoundary?: boolean; canRunSatelliteOperations?: boolean; }) {
  const [properties, setProperties] = useState<PortfolioProperty[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId ?? null);
  const [name, setName] = useState(""); const [boundarySource, setBoundarySource] = useState(""); const [geometry, setGeometry] = useState(""); const [drawPoints, setDrawPoints] = useState<Array<[number, number]>>([]);
  const [error, setError] = useState<string | null>(null); const [creating, setCreating] = useState(false); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setLoading(true); try { const result = await api.portfolio(tenantId); setProperties(result.items); } finally { setLoading(false); } }, [api, tenantId]);
  const portfolioGeometry: Geometry | null = properties.some(item => item.geometry_geojson) ? {
    type: "GeometryCollection",
    geometries: properties.flatMap(item => item.geometry_geojson ? [item.geometry_geojson] : []),
  } : null;
  useEffect(() => { void refresh().catch(() => setError("SOURCE_UNAVAILABLE — não foi possível carregar propriedades.")); }, [refresh]);
  useEffect(() => { if (!loading && selectedId && !properties.some(item => item.id === selectedId)) setSelectedId(null); }, [loading, properties, selectedId]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError(null); setCreating(true);
    try { const parsed = geometry ? JSON.parse(geometry) as PropertyCreate["geometry_geojson"] : { type: "Polygon", coordinates: [[...drawPoints, drawPoints[0]]] } as PropertyCreate["geometry_geojson"]; if (drawPoints.length < 3 && !geometry) throw new Error("draw at least three points"); const item = await api.createProperty(tenantId, { name, geometry_geojson: parsed, geometry_crs: "EPSG:4326", boundary_source: boundarySource || "CUSTOMER_DRAWN_IN_RIBEIRA_MAPS", classification: "MANUAL_CONFIRMED" }); await refresh(); setSelectedId(item.id); setName(""); setBoundarySource(""); setGeometry(""); setDrawPoints([]); }
    catch { setError("DADO_INSUFICIENTE — informe nome, GeoJSON válido em EPSG:4326 e origem verificável do limite."); }
    finally { setCreating(false); }
  };
  const drawnAoi: Geometry | null = drawPoints.length >= 3 ? { type: "Polygon", coordinates: [[...drawPoints, drawPoints[0]]] } : null;
  return <div className="workspace"><header><p className="eyebrow">Ribeira Maps</p><h1>Portfólio de propriedades</h1><p>Consulte os dados confirmados da sua propriedade e as análises disponíveis.</p></header><div className="workspace-grid"><aside className="property-nav"><h2>Portfólio</h2>{loading && <p>Carregando portfólio…</p>}{!loading && properties.length === 0 && <p>Nenhuma propriedade disponível.</p>}{portfolioGeometry && <section className="portfolio-map"><h3>Limites cadastrados</h3><MapCanvas aoi={portfolioGeometry} apiBaseUrl={apiBaseUrl} tileUrl={null} deltaTileUrl={null} ndviEnabled={false} deltaEnabled={false} token={token} /></section>}<div className="property-list">{properties.map(item => { const area = formatHectares(item.area_hectares); return <button type="button" className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>{customerPropertyName(item.name)}<small>{item.data_status === "READY" ? "Dados disponíveis" : "Dados básicos cadastrados"} · {area ? `${area} ha` : "área ainda não disponível"}</small></button>; })}</div>{canManageProperties && <details><summary>Nova propriedade</summary><form className="property-form" onSubmit={create}><label>Nome<input value={name} onChange={event => setName(event.target.value)} required maxLength={200} /></label><p>Comece desenhando o limite no mapa, importando um arquivo na etapa seguinte ou colando GeoJSON técnico.</p><MapCanvas aoi={drawnAoi} apiBaseUrl={apiBaseUrl} tileUrl={null} deltaTileUrl={null} ndviEnabled={false} deltaEnabled={false} token={token} onMapClick={(point) => setDrawPoints(points => [...points, point])} /><p>{drawPoints.length} vértices definidos. Clique no mapa para adicionar vértices.</p><button type="button" onClick={() => setDrawPoints(points => points.slice(0, -1))} disabled={!drawPoints.length}>Desfazer ponto</button><button type="button" onClick={() => setDrawPoints([])} disabled={!drawPoints.length}>Limpar desenho</button><label>Origem do limite<input value={boundarySource} onChange={event => setBoundarySource(event.target.value)} maxLength={500} placeholder="Desenhado no Ribeira Maps" /></label><details><summary>Usar GeoJSON técnico</summary><textarea value={geometry} onChange={event => setGeometry(event.target.value)} placeholder='{"type":"Polygon",...}' /></details><button type="submit" disabled={creating}>Confirmar propriedade</button></form></details>}{error && <p role="alert">{error}</p>}</aside><div className="workspace-content">{selectedId ? <Farm360Page key={selectedId} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} propertyId={selectedId} token={token} canManageBoundary={canManageBoundary} canRunSatelliteOperations={canRunSatelliteOperations} /> : <section className="state">Selecione uma propriedade do portfólio.</section>}</div></div></div>;
}
