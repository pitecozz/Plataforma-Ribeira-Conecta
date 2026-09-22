import { Fragment } from "react";
import type { DigitalTwinAsset } from "../../types/farm360";
import { Status } from "../../components/Status";
import "./AssetPanel.css";

function contextEntries(
  context: Record<string, unknown>,
): Array<[string, string]> {
  return Object.entries(context).map(([key, value]) => [
    key,
    typeof value === "string" ? value : JSON.stringify(value),
  ]);
}

export function AssetPanel({
  assets,
  selectedAssetId,
  onSelect,
  loadError = false,
}: {
  assets: DigitalTwinAsset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
  loadError?: boolean;
}) {
  const selected = assets.find((asset) => asset.id === selectedAssetId) ?? null;
  return (
    <section className="asset-panel">
      <h2>Ativos e contexto</h2>
      <p>Inventário persistido do Digital Twin. Ausências não são inferidas.</p>
      {loadError ? (
        <p role="alert">
          SOURCE_UNAVAILABLE — não foi possível carregar os ativos confirmados.
          Os demais dados da propriedade continuam acessíveis.
        </p>
      ) : assets.length === 0 ? (
        <p className="empty-state">
          DADO_INSUFICIENTE — nenhum ativo confirmado está vinculado a esta
          propriedade.
        </p>
      ) : (
        <div className="asset-list">
          {assets.map((asset) => (
            <button
              type="button"
              className={asset.id === selectedAssetId ? "selected" : ""}
              key={asset.id}
              onClick={() => onSelect(asset.id)}
            >
              <strong>{asset.name}</strong>
              <span>
                {asset.asset_type} · <Status value={asset.status} />
              </span>
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="asset-detail">
          <h3>{selected.name}</h3>
          <dl>
            <dt>Tipo</dt>
            <dd>{selected.asset_type}</dd>
            <dt>Status</dt>
            <dd>
              <Status value={selected.status} />
            </dd>
            <dt>Classificação</dt>
            <dd>
              <Status value={selected.classification} />
            </dd>
            <dt>Observado em</dt>
            <dd>{selected.observed_at ?? "UNKNOWN"}</dd>
            <dt>Fonte</dt>
            <dd>{selected.source_reference ?? "UNKNOWN"}</dd>
            <dt>Geometria</dt>
            <dd>
              {selected.geometry_geojson
                ? selected.geometry_geojson.type
                : "UNKNOWN"}
            </dd>
            <dt>CRS</dt>
            <dd>{selected.geometry_crs ?? "UNKNOWN"}</dd>
          </dl>
          {contextEntries(selected.context).length > 0 && (
            <>
              <h3>Contexto registrado</h3>
              <dl>
                {contextEntries(selected.context).map(([key, value]) => (
                  <Fragment key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl>
            </>
          )}
        </div>
      )}
    </section>
  );
}
