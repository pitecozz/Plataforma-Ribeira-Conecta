import type { Provenance } from "../../types/farm360";

export function ProvenancePanel({ provenance }: { provenance: Provenance | null }) {
  if (!provenance) return null;

  const isDelta = provenance.product.product_type === "NDVI_DELTA" || provenance.product.algorithm_id === "NDVI_TEMPORAL_DELTA";
  const directInputs = provenance.assets.map(asset => `${asset.asset_key} (${asset.checksum ?? "NULL"})`).join(", ");
  const upstreamScenes = provenance.upstreams?.map(upstream => upstream.scene?.scene_id ?? "UNKNOWN").join(" · ") ?? "";

  return <details className="provenance"><summary>Evidence Chain — de onde veio esta camada?</summary><ol><li><strong>Derived Product</strong><br />{provenance.product.id} · {provenance.product.checksum ?? "NULL"}<br />{provenance.product.algorithm_id} {provenance.product.algorithm_version} · {provenance.product.formula}</li><li><strong>Processing Job</strong><br />{provenance.processing_job.id ?? "UNKNOWN"} · {provenance.processing_job.status}</li><li><strong>{isDelta ? "Inputs diretos" : "Inputs deste produto"}</strong><br />{isDelta ? "Produtos derivados upstream" : directInputs || "DADO_INSUFICIENTE"}</li><li><strong>{isDelta ? "Sentinel scenes upstream" : "Sentinel scene"}</strong><br />{isDelta ? upstreamScenes || "DADO_INSUFICIENTE" : provenance.scene?.scene_id ?? "UNKNOWN"}</li><li><strong>Provider / STAC source</strong><br />{provenance.provider.id} · {provenance.provider.catalog_source}</li></ol>{provenance.upstreams?.length ? <><h3>{isDelta ? "Produtos upstream do delta — assets das cenas" : "Produtos upstream"}</h3><ul>{provenance.upstreams.map(upstream => <li key={upstream.relationship}><strong>{upstream.relationship}</strong><br />{upstream.product.id} · {upstream.scene?.scene_id ?? "UNKNOWN"}<br />{upstream.assets.map(asset => `${asset.asset_key} (${asset.checksum ?? "NULL"})`).join(", ") || "DADO_INSUFICIENTE"}</li>)}</ul></> : null}<h3>Evidências</h3><ul>{provenance.evidence.map(evidence => <li key={evidence.id}>{evidence.evidence_type} · {evidence.classification} · {evidence.observed_at ?? "UNKNOWN"}</li>)}</ul></details>;
}
