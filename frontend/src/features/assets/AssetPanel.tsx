import { Fragment } from "react";
import type { DigitalTwinAsset } from "../../types/farm360";
import { Status } from "../../components/Status";
import { customerAssetTypeLabel, customerDateLabel, customerSourceLabel } from "../../presentation";
import type { Farm360Api } from "../../api/client";
import { AssetRegistrationPanel } from "./AssetRegistrationPanel";
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
  api,
  tenantId,
  propertyId,
  canManageAssets = false,
  onCreated,
}: {
  assets: DigitalTwinAsset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
  loadError?: boolean;
  api?: Farm360Api;
  tenantId?: string;
  propertyId?: string;
  canManageAssets?: boolean;
  onCreated?: (asset: DigitalTwinAsset) => void;
}) {
  const selected = assets.find((asset) => asset.id === selectedAssetId) ?? null;
  return (
    <section className="asset-panel">
      <h2>Ativos confirmados{assets.length > 0 ? ` — ${assets.length}` : ""}</h2>
      <p>Selecione um ativo para localizá-lo no mapa e consultar seus dados confirmados.</p>
      {loadError ? (
        <p role="alert">
          Não foi possível atualizar os ativos confirmados agora.
          Os demais dados da propriedade continuam acessíveis.
        </p>
      ) : assets.length === 0 ? (
        <p className="empty-state">
          Ainda não há ativos confirmados vinculados a esta propriedade.
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
                {customerAssetTypeLabel(asset.asset_type)} · <Status value={asset.status} />
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
            <dd>{customerAssetTypeLabel(selected.asset_type)}</dd>
            <dt>Status</dt>
            <dd>
              <Status value={selected.status} />
            </dd>
            <dt>Localização</dt>
            <dd>{selected.geometry_geojson ? "Posição registrada no mapa" : "Localização ainda não registrada"}</dd>
            <dt>Confirmação</dt>
            <dd>
              <Status value={selected.classification} />
            </dd>
            <dt>Última observação</dt>
            <dd>{customerDateLabel(selected.observed_at)}</dd>
            <dt>Fonte</dt>
            <dd>{customerSourceLabel(selected.source_reference)}</dd>
            <dt>Contexto</dt>
            <dd>{contextEntries(selected.context).length > 0 ? "Informações complementares registradas" : "Ainda não disponível"}</dd>
          </dl>
          <details>
            <summary>Detalhes técnicos e proveniência</summary>
            <dl><dt>Identificador do ativo</dt><dd>{selected.id}</dd><dt>Tipo técnico</dt><dd>{selected.asset_type}</dd><dt>Fonte técnica</dt><dd>{selected.source_reference ?? "Não informada"}</dd><dt>Geometria</dt><dd>{selected.geometry_geojson ? selected.geometry_geojson.type : "Não disponível"}</dd><dt>CRS</dt><dd>{selected.geometry_crs ?? "Não informado"}</dd></dl>
            {contextEntries(selected.context).length > 0 && <><h3>Contexto registrado</h3><dl>
                {contextEntries(selected.context).map(([key, value]) => (
                  <Fragment key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl></>}
          </details>
        </div>
      )}
      {canManageAssets && api && tenantId && propertyId && onCreated && <AssetRegistrationPanel api={api} tenantId={tenantId} propertyId={propertyId} onCreated={onCreated} />}
    </section>
  );
}
