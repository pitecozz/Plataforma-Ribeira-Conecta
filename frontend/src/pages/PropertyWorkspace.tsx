import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { Farm360Api } from "../api/client";
import type { PropertyCreate, PropertyRecord } from "../types/farm360";
import { Farm360Page } from "./Farm360Page";

export function PropertyWorkspace({ api, apiBaseUrl, tenantId, token, initialPropertyId }: { api: Farm360Api; apiBaseUrl: string; tenantId: string; token: string; initialPropertyId?: string; }) {
  const [properties, setProperties] = useState<PropertyRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId ?? null);
  const [name, setName] = useState(""); const [boundarySource, setBoundarySource] = useState(""); const [geometry, setGeometry] = useState("");
  const [error, setError] = useState<string | null>(null); const [creating, setCreating] = useState(false);
  const refresh = useCallback(async () => { const result = await api.properties(tenantId); setProperties(result.items); }, [api, tenantId]);
  useEffect(() => { void refresh().catch(() => setError("SOURCE_UNAVAILABLE — não foi possível carregar propriedades.")); }, [refresh]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError(null); setCreating(true);
    try { const parsed = JSON.parse(geometry) as PropertyCreate["geometry_geojson"]; const item = await api.createProperty(tenantId, { name, geometry_geojson: parsed, geometry_crs: "EPSG:4326", boundary_source: boundarySource, classification: "MANUAL_CONFIRMED" }); await refresh(); setSelectedId(item.id); setName(""); setBoundarySource(""); setGeometry(""); }
    catch { setError("DADO_INSUFICIENTE — informe nome, GeoJSON válido em EPSG:4326 e origem verificável do limite."); }
    finally { setCreating(false); }
  };
  return <div className="workspace"><header><p className="eyebrow">Ribeira Maps</p><h1>Farm 360 operacional</h1><p>Dados persistidos e classificados; o dataset de validação permanece somente validação.</p></header><div className="workspace-grid"><aside className="property-nav"><h2>Propriedades</h2><div className="property-list">{properties.map(item => <button type="button" className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)}>{item.name}<small>{item.data_status} · {item.classification}</small></button>)}</div><details><summary>Nova propriedade</summary><form className="property-form" onSubmit={create}><label>Nome<input value={name} onChange={event => setName(event.target.value)} required maxLength={200} /></label><label>Origem do limite<input value={boundarySource} onChange={event => setBoundarySource(event.target.value)} required maxLength={500} placeholder="Ex.: levantamento manual confirmado" /></label><label>GeoJSON · EPSG:4326<textarea value={geometry} onChange={event => setGeometry(event.target.value)} required placeholder='{"type":"Polygon",...}' /></label><button type="submit" disabled={creating}>Criar propriedade</button></form></details>{error && <p role="alert">{error}</p>}</aside><div className="workspace-content">{selectedId ? <Farm360Page key={selectedId} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} propertyId={selectedId} token={token} /> : <section className="state">Selecione uma propriedade ou crie um limite com origem verificável.</section>}</div></div></div>;
}
