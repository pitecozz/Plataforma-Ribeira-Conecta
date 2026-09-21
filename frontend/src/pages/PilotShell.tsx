import { useState } from "react";

import type { Farm360Api } from "../api/client";
import { Status } from "../components/Status";
import { HomePage } from "./HomePage";
import { PropertyWorkspace } from "./PropertyWorkspace";
import "./PilotShell.css";

type View = "HOME" | "FARM360" | "HELP";

const moduleStates = [
  ["Farm360", "BETA"], ["Maps", "BETA"], ["Assets", "BETA"],
  ["Flood", "FOUNDATION"], ["Agro", "COMING_SOON"], ["Soil", "COMING_SOON"],
  ["IoT", "COMING_SOON"], ["Connect", "COMING_SOON"], ["Energy", "COMING_SOON"],
  ["Reports", "COMING_SOON"], ["Prospect", "COMING_SOON"], ["AI", "DEFERRED"],
] as const;

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
  const openFarm360 = (propertyId: string) => {
    setSelectedPropertyId(propertyId);
    setView("FARM360");
  };
  return <div className="pilot-shell"><header className="pilot-header"><div><p className="eyebrow">Ribeira Conecta</p><strong>piloto beta</strong></div><nav aria-label="Navegação principal"><button type="button" className={view === "HOME" ? "selected" : ""} onClick={() => setView("HOME")}>Home</button><button type="button" className={view === "FARM360" ? "selected" : ""} onClick={() => setView("FARM360")}>Farm360</button><button type="button" className={view === "HELP" ? "selected" : ""} onClick={() => setView("HELP")}>Ajuda</button></nav></header><aside className="module-status" aria-label="Estado dos módulos"><span>Estado da plataforma:</span>{moduleStates.map(([module, state]) => <span key={module}>{module} <Status value={state} /></span>)}</aside>{view === "HOME" && <HomePage api={api} tenantId={tenantId} onOpenFarm360={openFarm360} />}{view === "FARM360" && <PropertyWorkspace key={selectedPropertyId ?? "portfolio"} api={api} apiBaseUrl={apiBaseUrl} tenantId={tenantId} initialPropertyId={selectedPropertyId} token={token} />}{view === "HELP" && <main className="state"><h1>Ajuda do piloto</h1><p>Use Home para abrir uma propriedade e Farm360 para consultar limites, ativos e evidências disponíveis.</p><p>Resultados `UNKNOWN`, `DADO_INSUFICIENTE`, `SOURCE_UNAVAILABLE` e `INCONCLUSIVE` não devem ser substituídos por suposições.</p><p>Envie feedback pela propriedade no Farm360. Telemetria, adequação agrícola e automações ainda não estão disponíveis neste beta.</p></main>}</div>;
}
