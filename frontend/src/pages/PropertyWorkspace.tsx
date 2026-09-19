import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { Geometry } from "geojson";
import type { Farm360Api } from "../api/client";
import type { PropertyCreate, PortfolioProperty } from "../types/farm360";
import { MapCanvas } from "../features/map/MapCanvas";
import { Farm360Page } from "./Farm360Page";
import "./PropertyWorkspace.css";

export function PropertyWorkspace({ api, apiBaseUrl, tenantId, token, initialPropertyId }: { api: Farm360Api; apiBaseUrl: string; tenantId: string; token: string; initialPropertyId?: string; }) {
  const [properties, setProperties] = useState<PortfolioProperty[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId ?? null);
  const [name, setName] = useState(""); const [boundarySource, setBoundarySource] = useState(""); const [geometry, setGeometry] = useState("");
  const [error, setError] = useState<string | null>(null); const [creating, setCreating] = useState(false);
  const refresh = useCallback(async () => { const result = await api.portfolio(tenantId); setProperties(result.items); }, [api, tenantId]);
  const portfolioGeometry: Geometry | null = properties.some(item => item.geometry_geojson) ? {
    type: "GeometryCollection",
    geometries: properties.flatMap(item => item.geometry_geojson ? [item.geometry_geojson] : []),
  } : null;
  useEffect(() => { void refresh().catch(() => setError("SOURCE_UNAVAILABLE — não foi possível carregar propriedades.")); }, [refresh]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError(null); setCreating(true);
    try { const parsed = JSON.parse(geometry) as PropertyCreate["geometry_geojson"]; const item = await api.createProperty(tenantId, { name, geometry_geojson: parsed, geometry_crs: "EPSG:4326", boundary_source: boundarySource, classification: "MANUAL_CONFIRMED" }); await refresh(); setSelectedId(item.id); setName(""); setBoundarySource(""); setGeometry(""); }
    catch { setError("DADO_INSUFICIENTE — informe nome, GeoJSON válido em EPSG:4326 e origem verificável do limite."); }
    finally { setCreating(false); }
  };
  return <div className="workspace"><header><p className="eyebrow">Ribeira Maps</p><h1>Portfólio de propriedades</h1><p>Dados persistidos e classificados; TEST_AOI_ONLY permanece dado de validação.</p></header><div className="workspace-grid"><aside className="property-nav"><h2>Portfólio</h2>{portfolioGeometry && <section className="portfolio-map"><h3>Limites cadastrados</h3><MapCanvas aoi={portfolioGeometry} apiBaseUrl={apiBaseUrl} tileUrl={null} deltaTileUrl={null} ndviEnabled={false} deltaEnabled={false} token={token} /></section>}<div className="property-list">{properties.map(item => <button type="button" className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>{item.name}<small>{item.data_status} · {item.area_hectares ?? "UNKNOWN"} ha · jobs {Object.values(item.jobs).reduce((total, value) => total + value, 0)}</small></button>)}</div><details><summary>Nova propriedade GeoJSON</summary><form className="property-form" onSubmit={create}><label>Nome<input value={name} onChange={event => setName(event.target.value)} required maxLength={200} /></label><label>Origem do limite<input value={boundarySource} onChange={event => setBoundarySource(event.target.value)} required maxLength={500} placeholder="Ex.: levantamento manual confirmado" /></label><label>GeoJSON Polygon/MultiPolygon · EPSG:4326<textarea value={geometry} onChange={event => setGeometry(event.target.value)} required placeholder='{"type":"Polygon",...}' /></label><button type="submit" disabled={creating}>Criar propriedade</button></form></details>{error && <p role="alert">{error}</p>}</aside><div className="workspace-content">{selectedId ? <Farm360Page key={selectedId} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} propertyId={selectedId} token={token} /> : <section className="state">Selecione uma propriedade do portfólio.</section>}</div></div></div>;
}
