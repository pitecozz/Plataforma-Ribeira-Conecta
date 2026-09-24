import { useMemo, useState } from "react";
import type { Farm360Api } from "../../api/client";
import { MapCanvas } from "../map/MapCanvas";
import type { PropertyRecord } from "../../types/farm360";

type Point = [number, number];

function outerRing(property: PropertyRecord): Point[] {
  const geometry = property.geometry_geojson;
  if (!geometry || geometry.type !== "Polygon") return [];
  return (geometry.coordinates[0] ?? []).slice(0, -1) as Point[];
}

function validPoint(point: Point): boolean {
  return Number.isFinite(point[0]) && Number.isFinite(point[1])
    && point[0] >= -180 && point[0] <= 180
    && point[1] >= -90 && point[1] <= 90;
}

export function BoundaryEditorPanel({
  api,
  apiBaseUrl,
  tenantId,
  property,
  token,
  onChanged,
}: {
  api: Farm360Api;
  apiBaseUrl: string;
  tenantId: string;
  property: PropertyRecord;
  token: string;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [points, setPoints] = useState<Point[]>(() => outerRing(property));
  const [history, setHistory] = useState<Point[][]>([]);
  const [error, setError] = useState<string | null>(null);
  const geometry = useMemo(
    () => ({ type: "Polygon" as const, coordinates: [[...points, points[0]]] }),
    [points],
  );
  if (!property.geometry_geojson || property.geometry_geojson.type !== "Polygon" || !property.boundary_checksum) return null;
  const mutate = (next: Point[]) => {
    setHistory((items) => [...items, points]);
    setPoints(next);
  };
  const cancel = () => {
    setPoints(outerRing(property));
    setHistory([]);
    setEditing(false);
    setError(null);
  };
  const save = async () => {
    if (points.length < 3) {
      setError("Defina ao menos três vértices para salvar o limite.");
      return;
    }
    if (!points.every(validPoint)) {
      setError("Cada vértice precisa ter longitude entre −180 e 180 e latitude entre −90 e 90.");
      return;
    }
    try {
      await api.updateBoundary(tenantId, property.id, { geometry_geojson: geometry, geometry_crs: "EPSG:4326", boundary_source: "CUSTOMER_DRAWN_IN_RIBEIRA_MAPS", classification: "MANUAL_CONFIRMED", reason: "Limite revisado no Ribeira Maps", expected_checksum: property.boundary_checksum! });
      setEditing(false);
      setHistory([]);
      setError(null);
      onChanged();
    } catch {
      setError("Não foi possível salvar a nova versão do limite. Revise os vértices e tente novamente.");
    }
  };
  return (
    <section className="boundary-editor">
      <h2>Editar limite</h2>
      {!editing ? (
        <button type="button" onClick={() => { setPoints(outerRing(property)); setEditing(true); }}>
          Editar limite no mapa
        </button>
      ) : (
        <>
          <p>
            Clique no mapa para acrescentar um vértice ao rascunho ou ajuste as coordenadas abaixo.
            Nada é gravado até salvar uma nova versão.
          </p>
          <div className="boundary-editor-map">
            <MapCanvas
              aoi={geometry}
              apiBaseUrl={apiBaseUrl}
              tileUrl={null}
              deltaTileUrl={null}
              ndviEnabled={false}
              deltaEnabled={false}
              token={token}
              onMapClick={(point) => mutate([...points, point])}
            />
          </div>
          <ol>
            {points.map((point, index) => (
              <li key={`${point[0]}-${point[1]}-${index}`}>
                <label>Longitude <input aria-label={`Longitude ${index + 1}`} type="number" step="any" value={point[0]} onChange={(event) => mutate(points.map((item, itemIndex) => itemIndex === index ? [Number(event.target.value), item[1]] : item))} /></label>
                <label>Latitude <input aria-label={`Latitude ${index + 1}`} type="number" step="any" value={point[1]} onChange={(event) => mutate(points.map((item, itemIndex) => itemIndex === index ? [item[0], Number(event.target.value)] : item))} /></label>
                <button type="button" onClick={() => mutate(points.filter((_, itemIndex) => itemIndex !== index))}>Excluir</button>
              </li>
            ))}
          </ol>
          <button type="button" onClick={() => {
            const previous = history.at(-1);
            if (previous) {
              setPoints(previous);
              setHistory((items) => items.slice(0, -1));
            }
          }} disabled={!history.length}>Desfazer</button>
          <button type="button" onClick={cancel}>Cancelar</button>
          <button type="button" onClick={() => void save()}>Salvar nova versão</button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
