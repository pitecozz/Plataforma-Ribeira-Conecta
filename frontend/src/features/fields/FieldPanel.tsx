import { useMemo, useState, type FormEvent } from "react";
import type { Geometry } from "geojson";

import type { Farm360Api } from "../../api/client";
import { Status } from "../../components/Status";
import { customerDateLabel, customerSourceLabel } from "../../presentation";
import type { FieldContext } from "../../types/farm360";
import { MapCanvas } from "../map/MapCanvas";
import "./FieldPanel.css";

type Point = [number, number];

function isFieldGeometry(value: Geometry): boolean {
  return value.type === "Polygon" || value.type === "MultiPolygon";
}

function drawnGeometry(points: Point[]): Geometry {
  return { type: "Polygon", coordinates: [[...points, points[0]]] };
}

function FieldRegistration({ api, tenantId, propertyId, propertyGeometry, apiBaseUrl, token, onCreated }: {
  api: Farm360Api;
  tenantId: string;
  propertyId: string;
  propertyGeometry: Geometry | null;
  apiBaseUrl: string;
  token: string;
  onCreated: (field: FieldContext) => void;
}) {
  const [name, setName] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [geometry, setGeometry] = useState("");
  const [drawPoints, setDrawPoints] = useState<Point[]>([]);
  const [sourceReference, setSourceReference] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const draftGeometry = useMemo(
    () => drawPoints.length >= 3 ? drawnGeometry(drawPoints) : null,
    [drawPoints],
  );

  const addPoint = (point: Point) => {
    const next = [...drawPoints, point];
    setDrawPoints(next);
    setGeometry(next.length >= 3 ? JSON.stringify(drawnGeometry(next)) : "");
    setMessage(null);
  };

  const undoPoint = () => {
    const next = drawPoints.slice(0, -1);
    setDrawPoints(next);
    setGeometry(next.length >= 3 ? JSON.stringify(drawnGeometry(next)) : "");
  };

  const clearDrawing = () => {
    setDrawPoints([]);
    setGeometry("");
    setMessage(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    let geometryGeojson: Geometry;
    const observed = new Date(observedAt);
    try {
      geometryGeojson = JSON.parse(geometry) as Geometry;
      if (!name.trim() || !sourceReference.trim() || !isFieldGeometry(geometryGeojson) || Number.isNaN(observed.getTime())) {
        throw new Error("invalid field registration");
      }
    } catch {
      setMessage("DADO_INSUFICIENTE — informe nome, fonte, horário e desenhe o talhão ou forneça GeoJSON Polygon/MultiPolygon em WGS84.");
      return;
    }
    setSaving(true);
    try {
      const field = await api.registerField(tenantId, propertyId, {
        name: name.trim(),
        status,
        geometry_geojson: geometryGeojson,
        geometry_crs: "EPSG:4326",
        source_reference: sourceReference.trim(),
        observed_at: observed.toISOString(),
        classification: "MANUAL_CONFIRMED",
      });
      onCreated(field);
      setName("");
      setStatus("ACTIVE");
      setGeometry("");
      setDrawPoints([]);
      setSourceReference("");
      setObservedAt("");
      setMessage("Talhão registrado com fonte e evidência próprias.");
    } catch {
      setMessage("Não foi possível registrar o talhão. Confirme a contenção no limite atual, a permissão e os dados de origem.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="field-registration">
      <summary>Registrar talhão</summary>
      <p>Registre somente geometria e contexto factual. O talhão não é um limite legal, declaração de cultura, observação de solo ou recomendação agronômica.</p>
      {propertyGeometry && (
        <section className="field-drawing">
          <p>Selecione pelo menos três vértices no mapa. O desenho é provisório até o envio do formulário.</p>
          <MapCanvas
            aoi={draftGeometry ?? propertyGeometry}
            apiBaseUrl={apiBaseUrl}
            tileUrl={null}
            deltaTileUrl={null}
            ndviEnabled={false}
            deltaEnabled={false}
            token={token}
            onMapClick={addPoint}
          />
          <p>{drawPoints.length} vértice(s) selecionado(s).</p>
          <div className="field-drawing-actions">
            <button type="button" onClick={undoPoint} disabled={drawPoints.length === 0}>Desfazer último ponto</button>
            <button type="button" onClick={clearDrawing} disabled={drawPoints.length === 0}>Limpar desenho</button>
          </div>
        </section>
      )}
      <form onSubmit={submit}>
        <label>Nome<input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required /></label>
        <label>Status informado<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ACTIVE">Ativo</option><option value="INACTIVE">Inativo</option><option value="UNKNOWN">Ainda não informado</option></select></label>
        <label>Fonte ou referência de confirmação<input value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} maxLength={2000} required /></label>
        <label>Observado em<input aria-label="Talhão observado em" type="datetime-local" value={observedAt} onChange={(event) => setObservedAt(event.target.value)} required /></label>
        <label>GeoJSON técnico (WGS84)<textarea value={geometry} onChange={(event) => { setGeometry(event.target.value); setDrawPoints([]); }} placeholder='{"type":"Polygon",...}' required /></label>
        <p className="field-registration-note">A API verifica se toda a geometria está contida no limite persistido. Nada é recortado ou inferido pelo navegador.</p>
        <button type="submit" disabled={saving}>{saving ? "Registrando…" : "Registrar talhão"}</button>
      </form>
      {message && <p role="alert">{message}</p>}
    </details>
  );
}

export function FieldPanel({ fields, loadError = false, api, tenantId, propertyId, propertyGeometry = null, apiBaseUrl = "", token = "", canManageFields = false, onCreated }: {
  fields: FieldContext[];
  loadError?: boolean;
  api?: Farm360Api;
  tenantId?: string;
  propertyId?: string;
  propertyGeometry?: Geometry | null;
  apiBaseUrl?: string;
  token?: string;
  canManageFields?: boolean;
  onCreated?: (field: FieldContext) => void;
}) {
  return (
    <section className="field-panel">
      <h2>Talhões confirmados</h2>
      <p>Geometrias confirmadas para contexto espacial. Nenhum cultivo, condição ou diagnóstico é inferido.</p>
      {loadError && <p><Status value="UNKNOWN" /> Não foi possível consultar os talhões autorizados.</p>}
      {!loadError && fields.length === 0 && <p><Status value="DADO_INSUFICIENTE" /> — não há talhão confirmado para esta propriedade.</p>}
      <div className="field-list">
        {fields.map((field) => (
          <article key={field.id}>
            <h3>{field.name}</h3>
            <p>Status informado: {field.status}</p>
            <p>Fonte: {customerSourceLabel(field.source_reference)}</p>
            <p>Observado em: {customerDateLabel(field.observed_at)}</p>
            <details>
              <summary>Detalhes técnicos e proveniência</summary>
              <dl>
                <dt>Classificação</dt><dd>{field.classification}</dd>
                <dt>CRS</dt><dd>{field.geometry_crs}</dd>
                <dt>Versão do limite</dt><dd>{field.boundary_version}</dd>
                <dt>Checksum</dt><dd>{field.boundary_checksum}</dd>
                <dt>Evidência</dt><dd>{field.evidence_id}</dd>
              </dl>
            </details>
          </article>
        ))}
      </div>
      {canManageFields && api && tenantId && propertyId && onCreated && (
        <FieldRegistration
          api={api}
          tenantId={tenantId}
          propertyId={propertyId}
          propertyGeometry={propertyGeometry}
          apiBaseUrl={apiBaseUrl}
          token={token}
          onCreated={onCreated}
        />
      )}
    </section>
  );
}
