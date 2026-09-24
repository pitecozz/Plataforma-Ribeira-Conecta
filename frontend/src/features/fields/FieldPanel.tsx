import { useState, type FormEvent } from "react";
import type { Geometry } from "geojson";

import type { Farm360Api } from "../../api/client";
import { Status } from "../../components/Status";
import { customerDateLabel, customerSourceLabel } from "../../presentation";
import type { FieldContext } from "../../types/farm360";
import "./FieldPanel.css";

function isFieldGeometry(value: Geometry): boolean {
  return value.type === "Polygon" || value.type === "MultiPolygon";
}

function FieldRegistration({ api, tenantId, propertyId, onCreated }: {
  api: Farm360Api;
  tenantId: string;
  propertyId: string;
  onCreated: (field: FieldContext) => void;
}) {
  const [name, setName] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [geometry, setGeometry] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
      setMessage("DADO_INSUFICIENTE — informe nome, fonte, horário e GeoJSON Polygon ou MultiPolygon em WGS84.");
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
      setName(""); setStatus("ACTIVE"); setGeometry(""); setSourceReference(""); setObservedAt("");
      setMessage("Talhão registrado com fonte e evidência próprias.");
    } catch {
      setMessage("Não foi possível registrar o talhão. Confirme a contenção no limite atual, a permissão e os dados de origem.");
    } finally {
      setSaving(false);
    }
  };

  return <details className="field-registration"><summary>Registrar talhão</summary><p>Registre somente geometria e contexto factual. O talhão não é um limite legal, declaração de cultura, observação de solo ou recomendação agronômica.</p><form onSubmit={submit}><label>Nome<input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required /></label><label>Status informado<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ACTIVE">Ativo</option><option value="INACTIVE">Inativo</option><option value="UNKNOWN">Ainda não informado</option></select></label><label>Fonte ou referência de confirmação<input value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} maxLength={2000} required /></label><label>Observado em<input aria-label="Talhão observado em" type="datetime-local" value={observedAt} onChange={(event) => setObservedAt(event.target.value)} required /></label><label>GeoJSON técnico (WGS84)<textarea value={geometry} onChange={(event) => setGeometry(event.target.value)} placeholder='{"type":"Polygon",...}' required /></label><p className="field-registration-note">A API verifica se toda a geometria está contida no limite persistido. Nada é recortado ou inferido pelo navegador.</p><button type="submit" disabled={saving}>{saving ? "Registrando…" : "Registrar talhão"}</button></form>{message && <p role="alert">{message}</p>}</details>;
}

export function FieldPanel({ fields, loadError = false, api, tenantId, propertyId, canManageFields = false, onCreated }: {
  fields: FieldContext[];
  loadError?: boolean;
  api?: Farm360Api;
  tenantId?: string;
  propertyId?: string;
  canManageFields?: boolean;
  onCreated?: (field: FieldContext) => void;
}) {
  return <section className="field-panel"><h2>Talhões e contexto operacional{fields.length > 0 ? ` — ${fields.length}` : ""}</h2><p>Geometrias operacionais separadas do limite da propriedade, cada uma com fonte e tempo de observação.</p>{loadError ? <p role="alert">Não foi possível atualizar os talhões agora. O limite e os demais dados da propriedade continuam acessíveis.</p> : fields.length === 0 ? <p className="empty-state">DADO_INSUFICIENTE — não há talhão registrado para esta propriedade.</p> : <div className="field-list">{fields.map((field) => <article key={field.id}><h3>{field.name}</h3><dl><dt>Status</dt><dd><Status value={field.status} /></dd><dt>Geometria</dt><dd>{field.geometry_geojson.type} em WGS84</dd><dt>Confirmação</dt><dd><Status value={field.classification} /></dd><dt>Observado em</dt><dd>{customerDateLabel(field.observed_at)}</dd><dt>Fonte</dt><dd>{customerSourceLabel(field.source_reference)}</dd></dl><details><summary>Detalhes técnicos e proveniência</summary><dl><dt>Identificador</dt><dd>{field.id}</dd><dt>Evidência</dt><dd>{field.evidence_id ?? "Ainda não disponível para este registro"}</dd><dt>Versão do limite de referência</dt><dd>{field.boundary_version}</dd><dt>Checksum do limite de referência</dt><dd>{field.boundary_checksum}</dd><dt>CRS</dt><dd>{field.geometry_crs}</dd></dl></details></article>)}</div>}{canManageFields && api && tenantId && propertyId && onCreated && <FieldRegistration api={api} tenantId={tenantId} propertyId={propertyId} onCreated={onCreated} />}</section>;
}
