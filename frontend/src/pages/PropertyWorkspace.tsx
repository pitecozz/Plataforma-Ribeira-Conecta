import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import type { Geometry } from "geojson";
import type { Farm360Api } from "../api/client";
import type { PropertyCreate, PortfolioProperty } from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { formatHectares } from "../formatting";
import { customerPropertyName } from "../presentation";
import { Farm360Page } from "./Farm360Page";
import "./PropertyWorkspace.css";

type Point = [number, number];

function normalizedPropertyName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

function validPoint(point: Point): boolean {
  return Number.isFinite(point[0]) && Number.isFinite(point[1])
    && point[0] >= -180 && point[0] <= 180
    && point[1] >= -90 && point[1] <= 90;
}

function drawnGeometry(points: Point[]): PropertyCreate["geometry_geojson"] {
  return { type: "Polygon", coordinates: [[...points, points[0]]] };
}

export function PropertyWorkspace({ api, apiBaseUrl, tenantId, token, initialPropertyId, canManageProperties = false, canManageBoundary = false, canRunSatelliteOperations = false, canManageAssets = false, canCompleteActions = false, canEvaluateAssets = false }: { api: Farm360Api; apiBaseUrl: string; tenantId: string; token: string; initialPropertyId?: string; canManageProperties?: boolean; canManageBoundary?: boolean; canRunSatelliteOperations?: boolean; canManageAssets?: boolean; canCompleteActions?: boolean; canEvaluateAssets?: boolean; }) {
  const [properties, setProperties] = useState<PortfolioProperty[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId ?? null);
  const [propertyQuery, setPropertyQuery] = useState("");
  const [name, setName] = useState(""); const [boundarySource, setBoundarySource] = useState(""); const [geometry, setGeometry] = useState(""); const [drawPoints, setDrawPoints] = useState<Point[]>([]);
  const [error, setError] = useState<string | null>(null); const [creating, setCreating] = useState(false); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setLoading(true); try { const result = await api.portfolio(tenantId); setProperties(result.items); } finally { setLoading(false); } }, [api, tenantId]);
  const filteredProperties = useMemo(() => {
    const query = normalizedPropertyName(propertyQuery);
    return query ? properties.filter((item) => normalizedPropertyName(item.name).includes(query)) : properties;
  }, [properties, propertyQuery]);
  const portfolioGeometry: Geometry | null = filteredProperties.some(item => item.geometry_geojson) ? {
    type: "GeometryCollection",
    geometries: filteredProperties.flatMap(item => item.geometry_geojson ? [item.geometry_geojson] : []),
  } : null;
  useEffect(() => { void refresh().catch(() => setError("SOURCE_UNAVAILABLE — não foi possível carregar propriedades.")); }, [refresh]);
  useEffect(() => { if (!loading && selectedId && !properties.some(item => item.id === selectedId)) setSelectedId(null); }, [loading, properties, selectedId]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError(null);
    let parsed: PropertyCreate["geometry_geojson"];
    try {
      if (geometry.trim()) parsed = JSON.parse(geometry) as PropertyCreate["geometry_geojson"];
      else {
        if (drawPoints.length < 3 || !drawPoints.every(validPoint)) throw new Error("invalid drawn geometry");
        parsed = drawnGeometry(drawPoints);
      }
    } catch {
      setError("DADO_INSUFICIENTE — desenhe ao menos três vértices válidos em WGS84 ou informe GeoJSON técnico válido.");
      return;
    }
    setCreating(true);
    try { const item = await api.createProperty(tenantId, { name, geometry_geojson: parsed, geometry_crs: "EPSG:4326", boundary_source: boundarySource || "CUSTOMER_DRAWN_IN_RIBEIRA_MAPS", classification: "MANUAL_CONFIRMED" }); await refresh(); setSelectedId(item.id); setName(""); setBoundarySource(""); setGeometry(""); setDrawPoints([]); }
    catch { setError("DADO_INSUFICIENTE — o limite não foi confirmado. Revise a geometria e a origem; a validação do servidor permanece a autoridade."); }
    finally { setCreating(false); }
  };
  const drawnAoi: Geometry | null = drawPoints.length >= 3 ? drawnGeometry(drawPoints) : null;
  return <div className="workspace"><header><p className="eyebrow">Ribeira Maps</p><h1>Portfólio de propriedades</h1><p>Consulte os dados confirmados da sua propriedade e as análises disponíveis.</p></header><div className="workspace-grid"><aside className="property-nav"><h2>Portfólio</h2>{loading && <p>Carregando portfólio…</p>}{!loading && properties.length === 0 && <p>Nenhuma propriedade disponível.</p>}{!loading && properties.length > 0 && <label className="property-search">Buscar pelo nome cadastrado<input type="search" value={propertyQuery} onChange={(event) => setPropertyQuery(event.target.value)} placeholder="Nome da propriedade" /></label>}{!loading && propertyQuery.trim() && <p className="property-search-status">{filteredProperties.length} de {properties.length} propriedades exibidas.</p>}{!loading && properties.length > 0 && filteredProperties.length === 0 && <p>Nenhuma propriedade corresponde ao nome informado.</p>}{portfolioGeometry && <section className="portfolio-map"><h3>Limites cadastrados</h3><MapCanvas aoi={portfolioGeometry} apiBaseUrl={apiBaseUrl} tileUrl={null} deltaTileUrl={null} ndviEnabled={false} deltaEnabled={false} token={token} /></section>}<div className="property-list">{filteredProperties.map(item => { const area = formatHectares(item.area_hectares); return <button type="button" className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>{customerPropertyName(item.name)}<small>{item.data_status === "READY" ? "Dados disponíveis" : "Dados básicos cadastrados"} · {area ? `${area} ha` : "área ainda não disponível"}</small></button>; })}</div>{canManageProperties && <details><summary>Nova propriedade</summary><form className="property-form" onSubmit={create}><label>Nome<input value={name} onChange={event => setName(event.target.value)} required maxLength={200} /></label><p>Desenhe o limite no mapa ou informe GeoJSON técnico. O desenho é um rascunho local até a confirmação; não é título ou levantamento legal.</p><MapCanvas aoi={drawnAoi} apiBaseUrl={apiBaseUrl} tileUrl={null} deltaTileUrl={null} ndviEnabled={false} deltaEnabled={false} token={token} onMapClick={(point) => setDrawPoints(points => [...points, point])} /><p>{drawPoints.length} vértice(s) no rascunho. Clique no mapa para acrescentar um vértice e revise as coordenadas antes de confirmar.</p>{drawPoints.length > 0 && <ol className="property-draft-coordinates">{drawPoints.map((point, index) => <li key={`${index}-${point[0]}-${point[1]}`}><label>Longitude<input aria-label={`Longitude do vértice ${index + 1}`} type="number" step="any" value={point[0]} onChange={(event) => setDrawPoints(points => points.map((item, itemIndex) => itemIndex === index ? [Number(event.target.value), item[1]] : item))} /></label><label>Latitude<input aria-label={`Latitude do vértice ${index + 1}`} type="number" step="any" value={point[1]} onChange={(event) => setDrawPoints(points => points.map((item, itemIndex) => itemIndex === index ? [item[0], Number(event.target.value)] : item))} /></label><button type="button" className="property-draft-remove" onClick={() => setDrawPoints(points => points.filter((_, itemIndex) => itemIndex !== index))}>Excluir</button></li>)}</ol>}<div className="property-draft-actions"><button type="button" onClick={() => setDrawPoints(points => points.slice(0, -1))} disabled={!drawPoints.length}>Desfazer ponto</button><button type="button" onClick={() => setDrawPoints([])} disabled={!drawPoints.length}>Limpar desenho</button></div><label>Origem do limite<input value={boundarySource} onChange={event => setBoundarySource(event.target.value)} maxLength={500} placeholder="Desenhado no Ribeira Maps" /></label><details><summary>Usar GeoJSON técnico</summary><textarea value={geometry} onChange={event => setGeometry(event.target.value)} placeholder='{"type":"Polygon",...}' /></details><button type="submit" disabled={creating}>Confirmar propriedade</button></form></details>}{error && <p role="alert">{error}</p>}</aside><div className="workspace-content">{selectedId ? <Farm360Page key={selectedId} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} propertyId={selectedId} token={token} canManageBoundary={canManageBoundary} canManageProperties={canManageProperties} canRunSatelliteOperations={canRunSatelliteOperations} canManageAssets={canManageAssets} canCompleteActions={canCompleteActions} canEvaluateAssets={canEvaluateAssets} /> : <section className="state">Selecione uma propriedade do portfólio.</section>}</div></div></div>;
}
