import { useMemo, useState } from "react";
import type { Farm360Api } from "../../api/client";
import type { PropertyRecord } from "../../types/farm360";

type Point = [number, number];

function outerRing(property: PropertyRecord): Point[] {
  const geometry = property.geometry_geojson;
  if (!geometry || geometry.type !== "Polygon") return [];
  return (geometry.coordinates[0] ?? []).slice(0, -1) as Point[];
}

export function BoundaryEditorPanel({ api, tenantId, property, onChanged }: { api: Farm360Api; tenantId: string; property: PropertyRecord; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [points, setPoints] = useState<Point[]>(() => outerRing(property));
  const [history, setHistory] = useState<Point[][]>([]);
  const [error, setError] = useState<string | null>(null);
  const geometry = useMemo(() => ({ type: "Polygon" as const, coordinates: [[...points, points[0]]] }), [points]);
  if (!property.geometry_geojson || property.geometry_geojson.type !== "Polygon" || !property.boundary_checksum) return null;
  const mutate = (next: Point[]) => { setHistory(items => [...items, points]); setPoints(next); };
  const save = async () => {
    if (points.length < 3) { setError("Defina ao menos três vértices para salvar o limite."); return; }
    try {
      await api.updateBoundary(tenantId, property.id, { geometry_geojson: geometry, geometry_crs: "EPSG:4326", boundary_source: "CUSTOMER_DRAWN_IN_RIBEIRA_MAPS", classification: "MANUAL_CONFIRMED", reason: "Limite revisado no Ribeira Maps", expected_checksum: property.boundary_checksum! });
      setEditing(false); setHistory([]); setError(null); onChanged();
    } catch { setError("Não foi possível salvar a nova versão do limite. Revise os vértices e tente novamente."); }
  };
  return <section className="boundary-editor"><h2>Editar limite</h2>{!editing ? <button type="button" onClick={() => { setPoints(outerRing(property)); setEditing(true); }}>Editar limite no mapa</button> : <><p>Edite a sequência de vértices. Alterações só são gravadas ao salvar uma nova versão.</p><ol>{points.map((point, index) => <li key={`${point[0]}-${point[1]}-${index}`}><label>Longitude <input aria-label={`Longitude ${index + 1}`} type="number" step="any" value={point[0]} onChange={event => mutate(points.map((item, itemIndex) => itemIndex === index ? [Number(event.target.value), item[1]] : item))} /></label><label>Latitude <input aria-label={`Latitude ${index + 1}`} type="number" step="any" value={point[1]} onChange={event => mutate(points.map((item, itemIndex) => itemIndex === index ? [item[0], Number(event.target.value)] : item))} /></label><button type="button" onClick={() => mutate(points.filter((_, itemIndex) => itemIndex !== index))}>Excluir</button></li>)}</ol><button type="button" onClick={() => mutate([...points, points.at(-1) ?? points[0]])}>Adicionar vértice</button><button type="button" onClick={() => { const previous = history.at(-1); if (previous) { setPoints(previous); setHistory(items => items.slice(0, -1)); } }} disabled={!history.length}>Desfazer</button><button type="button" onClick={() => { setPoints(outerRing(property)); setHistory([]); setEditing(false); setError(null); }}>Cancelar</button><button type="button" onClick={() => void save()}>Salvar nova versão</button></>}{error && <p role="alert">{error}</p>}</section>;
}
