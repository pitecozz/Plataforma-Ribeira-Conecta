import { useCallback, useEffect, useState } from "react";

import type { Farm360Api } from "../../api/client";
import type {
  BoundaryImport,
  BoundaryImportPreview,
  PropertyRecord,
} from "../../types/farm360";
import { Status } from "../../components/Status";

const MAX_BYTES = 1_000_000;

function shortHash(value: string | null) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "UNKNOWN";
}

export function BoundaryImportPanel({
  api,
  tenantId,
  property,
  onBoundaryChanged,
}: {
  api: Farm360Api;
  tenantId: string;
  property: PropertyRecord;
  onBoundaryChanged: () => Promise<void>;
}) {
  const [items, setItems] = useState<BoundaryImport[]>([]);
  const [selected, setSelected] = useState<BoundaryImport | null>(null);
  const [preview, setPreview] = useState<BoundaryImportPreview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const response = await api.boundaryImports(tenantId, property.id);
    setItems(response.items);
  }, [api, property.id, tenantId]);

  useEffect(() => {
    void refresh().catch(() => setError("SOURCE_UNAVAILABLE"));
  }, [refresh]);

  async function select(item: BoundaryImport) {
    setSelected(item);
    setPreview(null);
    setError(null);
    try {
      setPreview(await api.boundaryImportPreview(tenantId, item.id));
    } catch {
      setError("SOURCE_UNAVAILABLE");
    }
  }

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !source.trim()) return;
    if (file.size > MAX_BYTES) {
      setError("BOUNDARY_IMPORT_TOO_LARGE");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const created = await api.uploadBoundaryImport(
        tenantId,
        property.id,
        file,
        source,
        "MANUAL_CONFIRMED",
        "EPSG:4326",
      );
      await select(created);
      setFile(null);
      setSource("");
      await refresh();
    } catch {
      setError("BOUNDARY_IMPORT_FAILED");
    } finally {
      setLoading(false);
    }
  }

  async function review(action: "approve" | "reject") {
    if (!selected || !reason.trim() || selected.status !== "NEEDS_REVIEW") return;
    setLoading(true);
    setError(null);
    try {
      const result =
        action === "approve"
          ? await api.approveBoundaryImport(
              tenantId,
              selected.id,
              reason,
              selected.expected_property_checksum ?? "",
            )
          : await api.rejectBoundaryImport(tenantId, selected.id, reason);
      await select(result);
      await refresh();
      if (action === "approve") await onBoundaryChanged();
    } catch {
      setError(
        action === "approve"
          ? "BOUNDARY_IMPORT_CONFLICT"
          : "BOUNDARY_IMPORT_FAILED",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="boundary-import">
      <h2>Importar limite</h2>
      <p>
        GeoJSON, KML ou KMZ. O upload preserva o arquivo como evidência e nunca
        altera o limite até aprovação humana. KML/KMZ aceitam somente um polígono WGS84 e não transformam nem corrigem a geometria.
      </p>
      <form noValidate onSubmit={upload}>
        <label>
          Arquivo GeoJSON, KML ou KMZ
          <input
            aria-label="Arquivo GeoJSON, KML ou KMZ"
            type="file"
            accept=".geojson,.json,.kml,.kmz,application/geo+json,application/json,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
        </label>
        <label>
          Origem do limite
          <input
            aria-label="Origem do import"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            maxLength={500}
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          Enviar para revisão
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      <ul className="boundary-import-list">
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => void select(item)}>
              {item.original_filename} · <Status value={item.status} />
            </button>
          </li>
        ))}
      </ul>
      {selected && (
        <div className="boundary-preview">
          <h3>Preview de evidência</h3>
          <dl>
            <dt>Status</dt><dd><Status value={selected.status} /></dd>
            <dt>Arquivo SHA-256</dt><dd>{shortHash(selected.file_sha256)}</dd>
            <dt>Geometry SHA-256</dt><dd>{shortHash(selected.geometry_checksum)}</dd>
            <dt>CRS</dt><dd>{selected.original_crs ?? "UNKNOWN"} → {selected.target_crs ?? "UNKNOWN"}</dd>
            <dt>Área atual / importada</dt><dd>{preview ? `${preview.current_area_hectares ?? "UNKNOWN"} / ${preview.imported_area_hectares ?? "UNKNOWN"} ha` : "Carregando…"}</dd>
            <dt>Δ área</dt><dd>{preview ? `${preview.absolute_area_delta_hectares ?? "UNKNOWN"} ha (${preview.percentage_area_delta ?? "UNKNOWN"}%)` : "UNKNOWN"}</dd>
            <dt>Warnings</dt><dd>{selected.warnings.length ? selected.warnings.join(", ") : "NONE"}</dd>
          </dl>
          {selected.status === "NEEDS_REVIEW" && (
            <>
              <label>
                Razão da revisão
                <textarea
                  aria-label="Razão da revisão"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  maxLength={500}
                  required
                />
              </label>
              <div className="review-actions">
                <button
                  type="button"
                  disabled={loading || !selected.target_crs || !selected.expected_property_checksum}
                  onClick={() => void review("approve")}
                >
                  Aprovar limite
                </button>
                <button type="button" disabled={loading} onClick={() => void review("reject")}>
                  Rejeitar importação
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
