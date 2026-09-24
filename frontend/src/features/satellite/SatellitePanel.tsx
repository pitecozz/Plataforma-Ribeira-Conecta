import type { Scene } from "../../types/farm360";
import { customerDateLabel } from "../../presentation";

function newestScene(scenes: Scene[]): Scene | null {
  return [...scenes].sort(
    (left, right) => Date.parse(right.acquisition_datetime) - Date.parse(left.acquisition_datetime),
  )[0] ?? null;
}

export function SatellitePanel({
  scene,
  scenes = [],
}: {
  scene: Scene | null;
  scenes?: Scene[];
}) {
  const catalogued = scene ?? newestScene(scenes);
  if (!catalogued) {
    return <section><h2>Satélite</h2><p>Sem dados disponíveis para esta propriedade.</p></section>;
  }
  const isDerivedProductSource = scene !== null;
  return (
    <section>
      <h2>Sentinel-2</h2>
      <p>
        {isDerivedProductSource
          ? "Cena vinculada ao produto selecionado."
          : "Cena catalogada para esta propriedade; ainda não há produto derivado disponível."}
      </p>
      <dl>
        <dt>Cenas catalogadas</dt><dd>{scenes.length}</dd>
        <dt>Aquisição</dt><dd>{customerDateLabel(catalogued.acquisition_datetime)}</dd>
        <dt>Cobertura de nuvens reportada</dt><dd>{catalogued.cloud_cover ? `${catalogued.cloud_cover}%` : "Ainda não informado"}</dd>
        <dt>Disponibilidade</dt><dd>Metadados da cena catalogados</dd>
      </dl>
      <details>
        <summary>Detalhes técnicos e proveniência</summary>
        <dl>
          <dt>Fonte</dt><dd>{catalogued.provider} / {catalogued.collection}</dd>
          <dt>Identificador da cena</dt><dd>{catalogued.scene_id}</dd>
          <dt>Status técnico</dt><dd>{catalogued.source_status}</dd>
          <dt>Checksum</dt><dd>{catalogued.checksum}</dd>
        </dl>
        <h3>Assets catalogados</h3>
        <ul>{catalogued.assets.map(asset => <li key={asset.id}>{asset.asset_key}: {asset.title ?? "Ainda não informado"}</li>)}</ul>
      </details>
    </section>
  );
}
