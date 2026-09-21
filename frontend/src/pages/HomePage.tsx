import { useCallback, useEffect, useMemo, useState } from "react";

import type { Farm360Api } from "../api/client";
import type { PortfolioProperty } from "../types/farm360";
import { Status } from "../components/Status";
import "./HomePage.css";

export function HomePage({
  api,
  tenantId,
  onOpenFarm360,
}: {
  api: Farm360Api;
  tenantId: string;
  onOpenFarm360: (propertyId: string) => void;
}) {
  const [properties, setProperties] = useState<PortfolioProperty[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.portfolio(tenantId);
      setProperties(result.items);
    } catch {
      setError("SOURCE_UNAVAILABLE — não foi possível carregar o resumo do portfólio.");
    } finally {
      setLoading(false);
    }
  }, [api, tenantId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const contextAvailable = useMemo(
    () => properties.filter((property) => property.provenance_available).length,
    [properties],
  );
  const incomplete = useMemo(
    () => properties.filter((property) => property.data_status !== "READY").length,
    [properties],
  );

  return (
    <main className="home-page">
      <section className="home-intro">
        <p className="eyebrow">Ribeira Conecta · piloto beta</p>
        <h1>Visão geral</h1>
        <p>
          Este resumo usa apenas propriedades e contexto persistidos no seu
          tenant. Dados ausentes continuam explícitos.
        </p>
      </section>
      {loading && <p className="state">Carregando resumo…</p>}
      {error && <p className="state" role="alert">{error}</p>}
      {!loading && !error && <>
        <section className="home-cards" aria-label="Resumo do portfólio">
          <article><span>Propriedades</span><strong>{properties.length}</strong><small>registros acessíveis ao seu tenant</small></article>
          <article><span>Contexto com proveniência</span><strong>{contextAvailable}</strong><small>propriedades com produto persistido</small></article>
          <article><span>Contexto incompleto</span><strong>{incomplete}</strong><small>não é substituído por estimativa</small></article>
        </section>
        <section className="home-properties">
          <div><h2>Propriedades</h2><button type="button" onClick={() => void refresh()}>Atualizar</button></div>
          {properties.length === 0 ? <p className="empty-state">DADO_INSUFICIENTE — nenhuma propriedade está disponível para este tenant.</p> : <div className="home-property-list">{properties.map((property) => <article key={property.id}><h3>{property.name}</h3><p><Status value={property.data_status} /> · área {property.area_hectares ?? "UNKNOWN"} ha</p><dl><dt>Última cena</dt><dd>{property.latest_scene_at ?? "UNKNOWN"}</dd><dt>Contexto</dt><dd>{property.provenance_available ? "proveniência disponível" : "UNKNOWN"}</dd></dl><button type="button" onClick={() => onOpenFarm360(property.id)}>Abrir Farm360</button></article>)}</div>}
        </section>
      </>}
    </main>
  );
}
