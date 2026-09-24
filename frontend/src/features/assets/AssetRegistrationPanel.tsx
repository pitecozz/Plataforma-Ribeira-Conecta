import { useState, type FormEvent } from "react";

import type { Farm360Api } from "../../api/client";
import type { AssetCreate, DigitalTwinAsset } from "../../types/farm360";

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function coordinates(longitude: string, latitude: string): [number, number] | null {
  const hasLongitude = longitude.trim() !== "";
  const hasLatitude = latitude.trim() !== "";
  if (!hasLongitude && !hasLatitude) return null;
  const parsedLongitude = Number(longitude);
  const parsedLatitude = Number(latitude);
  if (!hasLongitude || !hasLatitude || !Number.isFinite(parsedLongitude) || !Number.isFinite(parsedLatitude) || parsedLongitude < -180 || parsedLongitude > 180 || parsedLatitude < -90 || parsedLatitude > 90) throw new Error("coordinates are invalid");
  return [parsedLongitude, parsedLatitude];
}

export function AssetRegistrationPanel({ api, tenantId, propertyId, onCreated }: { api: Farm360Api; tenantId: string; propertyId: string; onCreated: (asset: DigitalTwinAsset) => void; }) {
  const [name, setName] = useState(""); const [assetType, setAssetType] = useState(""); const [status, setStatus] = useState("ACTIVE");
  const [serialNumber, setSerialNumber] = useState(""); const [sourceReference, setSourceReference] = useState(""); const [observedAt, setObservedAt] = useState("");
  const [longitude, setLongitude] = useState(""); const [latitude, setLatitude] = useState(""); const [saving, setSaving] = useState(false); const [message, setMessage] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setMessage(null);
    try {
      const point = coordinates(longitude, latitude); const observed = new Date(observedAt);
      if (!name.trim() || !assetType.trim() || !sourceReference.trim() || Number.isNaN(observed.getTime())) throw new Error("missing factual fields");
      const payload: AssetCreate = { asset_type: assetType.trim(), name: name.trim(), serial_number: optionalText(serialNumber), status, property_id: propertyId, geometry: point ? { type: "Point", coordinates: point } : null, geometry_crs: point ? "EPSG:4326" : null, source_reference: sourceReference.trim(), observed_at: observed.toISOString(), context: {}, classification: "MANUAL_CONFIRMED" };
      setSaving(true); const asset = await api.registerAsset(tenantId, payload); onCreated(asset);
      setName(""); setAssetType(""); setStatus("ACTIVE"); setSerialNumber(""); setSourceReference(""); setObservedAt(""); setLongitude(""); setLatitude(""); setMessage("Ativo confirmado e vinculado à propriedade.");
    } catch { setMessage("DADO_INSUFICIENTE — informe nome, tipo, fonte, data de observação e, se houver localização, longitude e latitude válidas."); }
    finally { setSaving(false); }
  };
  return <section className="asset-registration"><h2>Registrar ativo confirmado</h2><p>Registre apenas dados observados ou confirmados. A localização é opcional e permanece ausente quando não foi registrada.</p><form onSubmit={submit}><label>Nome do ativo<input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required /></label><label>Tipo técnico<input value={assetType} onChange={(event) => setAssetType(event.target.value)} maxLength={100} placeholder="Ex.: RAIN_GAUGE" required /></label><label>Status informado<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ACTIVE">Ativo</option><option value="INACTIVE">Inativo</option><option value="RETIRED">Desativado</option><option value="UNKNOWN">Ainda não informado</option></select></label><label>Número de série (opcional)<input value={serialNumber} onChange={(event) => setSerialNumber(event.target.value)} maxLength={200} /></label><label>Fonte ou referência de confirmação<input value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} maxLength={2000} required /></label><label>Observado em<input aria-label="Observado em" type="datetime-local" value={observedAt} onChange={(event) => setObservedAt(event.target.value)} required /></label><fieldset><legend>Localização no mapa (opcional)</legend><label>Longitude<input aria-label="Longitude do ativo" type="number" step="any" min="-180" max="180" value={longitude} onChange={(event) => setLongitude(event.target.value)} /></label><label>Latitude<input aria-label="Latitude do ativo" type="number" step="any" min="-90" max="90" value={latitude} onChange={(event) => setLatitude(event.target.value)} /></label></fieldset><p className="asset-registration-note">O registro será classificado como confirmado manualmente; ele não confirma cobertura, condição técnica ou disponibilidade de serviço além dos dados informados.</p><button type="submit" disabled={saving}>{saving ? "Registrando…" : "Registrar ativo"}</button></form>{message && <p role="alert">{message}</p>}</section>;
}
