import { Fragment, useState } from "react";
import type { Geometry } from "geojson";
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

function AssetRuleEvaluation({ api, tenantId, asset, onEvaluated }: {
  api: Farm360Api;
  tenantId: string;
  asset: DigitalTwinAsset;
  onEvaluated: () => Promise<void> | void;
}) {
  const [evaluating, setEvaluating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const canEvaluate = Boolean(asset.evidence_id);
  const evaluate = async () => {
    setEvaluating(true);
    setMessage(null);
    try {
      await api.evaluateAsset(tenantId, asset.id);
      await onEvaluated();
      setMessage("Avaliação registrada no histórico desta propriedade. Consulte a decisão e suas limitações em Riscos e decisões.");
    } catch {
      setMessage("Não foi possível registrar a avaliação agora. Confirme a permissão e tente novamente.");
    } finally {
      setEvaluating(false);
    }
  };
  return <details className="asset-rule-evaluation"><summary>Avaliar regras para este ativo</summary><p>Esta ação usa o ativo somente como contexto de aplicabilidade. Ela não transforma o cadastro do ativo em medição, condição ou diagnóstico.</p>{!canEvaluate && <p>Não há evidência de cadastro disponível para este ativo. A avaliação permanece indisponível até que o registro tenha proveniência.</p>}<button type="button" onClick={() => void evaluate()} disabled={evaluating || !canEvaluate}>{evaluating ? "Avaliando…" : "Avaliar evidências e regras"}</button>{message && <p role="alert">{message}</p>}</details>;
}

export function AssetPanel({
  assets,
  selectedAssetId,
  onSelect,
  loadError = false,
  api,
  tenantId,
  propertyId,
  propertyGeometry = null,
  apiBaseUrl,
  token,
  canManageAssets = false,
  onCreated,
  canEvaluateAssets = false,
  onEvaluated,
}: {
  assets: DigitalTwinAsset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
  loadError?: boolean;
  api?: Farm360Api;
  tenantId?: string;
  propertyId?: string;
  propertyGeometry?: Geometry | null;
  apiBaseUrl?: string;
  token?: string;
  canManageAssets?: boolean;
  onCreated?: (asset: DigitalTwinAsset) => void;
  canEvaluateAssets?: boolean;
  onEvaluated?: () => Promise<void> | void;
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
            <dl><dt>Identificador do ativo</dt><dd>{selected.id}</dd><dt>Identificador de evidência</dt><dd>{selected.evidence_id ?? "Ainda não disponível para este registro"}</dd><dt>Tipo técnico</dt><dd>{selected.asset_type}</dd><dt>Fonte técnica</dt><dd>{selected.source_reference ?? "Não informada"}</dd><dt>Geometria</dt><dd>{selected.geometry_geojson ? selected.geometry_geojson.type : "Não disponível"}</dd><dt>CRS</dt><dd>{selected.geometry_crs ?? "Não informado"}</dd></dl>
            {contextEntries(selected.context).length > 0 && <><h3>Contexto registrado</h3><dl>
                {contextEntries(selected.context).map(([key, value]) => (
                  <Fragment key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl></>}
          </details>
          {canEvaluateAssets && api && tenantId && onEvaluated && <AssetRuleEvaluation api={api} tenantId={tenantId} asset={selected} onEvaluated={onEvaluated} />}
        </div>
      )}
      {canManageAssets && api && tenantId && propertyId && onCreated && <AssetRegistrationPanel api={api} tenantId={tenantId} propertyId={propertyId} propertyGeometry={propertyGeometry} apiBaseUrl={apiBaseUrl} token={token} onCreated={onCreated} />}
    </section>
  );
}
