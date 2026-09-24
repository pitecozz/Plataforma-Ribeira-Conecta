import { useEffect, useState } from "react";

import type { Farm360Api } from "../api/client";
import { HomePage } from "./HomePage";
import { PropertyWorkspace } from "./PropertyWorkspace";
import "./PilotShell.css";

type View = "HOME" | "FARM360" | "HELP";

export function PilotShell({
  api,
  apiBaseUrl,
  tenantId,
  token,
  initialPropertyId,
}: {
  api: Farm360Api;
  apiBaseUrl: string;
  tenantId: string;
  token: string;
  initialPropertyId?: string;
}) {
  const [view, setView] = useState<View>("HOME");
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | undefined>(initialPropertyId);
  const [permissions, setPermissions] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    let active = true;
    void api.access(tenantId).then((result) => {
      if (active) setPermissions(new Set(result.permissions));
    }).catch(() => {
      // Default-deny is intentional: a read-only customer view is safer than
      // exposing an operator control while the profile cannot be read.
      if (active) setPermissions(new Set());
    });
    return () => { active = false; };
  }, [api, tenantId]);
  const canManageProperties = permissions.has("property:write");
  const canManageBoundary = permissions.has("tenant:manage");
  const canRunSatelliteOperations = permissions.has("geospatial:search") && permissions.has("geospatial:process");
  const openFarm360 = (propertyId: string) => {
    setSelectedPropertyId(propertyId);
    setView("FARM360");
  };
  return (
    <div className="pilot-shell">
      <header className="pilot-header">
        <div><p className="eyebrow">Ribeira Conecta</p><strong>piloto beta</strong></div>
        <nav aria-label="Navegação principal">
          <button type="button" className={view === "HOME" ? "selected" : ""} onClick={() => setView("HOME")}>Visão geral</button>
          <button type="button" className={view === "FARM360" ? "selected" : ""} onClick={() => setView("FARM360")}>Farm360</button>
          <button type="button" className={view === "HELP" ? "selected" : ""} onClick={() => setView("HELP")}>Ajuda</button>
        </nav>
      </header>
      {view === "HOME" && <HomePage api={api} tenantId={tenantId} onOpenFarm360={openFarm360} />}
      {view === "FARM360" && <PropertyWorkspace key={selectedPropertyId ?? "portfolio"} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} initialPropertyId={selectedPropertyId} token={token} canManageProperties={canManageProperties} canManageBoundary={canManageBoundary} canRunSatelliteOperations={canRunSatelliteOperations} />}
      {view === "HELP" && <main className="state"><h1>Ajuda do piloto</h1><p>Use a Visão geral para abrir uma propriedade e o Farm360 para consultar limite, ativos e evidências disponíveis.</p><p>Quando uma análise ainda não está disponível, a tela explica o que falta. Nenhuma conclusão é criada por suposição.</p><p>Envie feedback pela propriedade no Farm360. Telemetria, adequação agrícola e automações ainda não estão disponíveis neste beta.</p></main>}
    </div>
  );
}
