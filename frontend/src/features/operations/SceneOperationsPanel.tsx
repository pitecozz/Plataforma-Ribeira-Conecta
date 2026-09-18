import { useState, type FormEvent } from "react";
import type { Farm360Api } from "../../api/client";
import type { ProcessingJob, Scene, SearchResult } from "../../types/farm360";
import { Status } from "../../components/Status";

function presentationStatus(status: string) { return status === "PENDING" ? "QUEUED" : status; }

export function SceneOperationsPanel({ api, tenantId, propertyId, scenes, onChanged }: { api: Farm360Api; tenantId: string; propertyId: string; scenes: Scene[]; onChanged: () => Promise<void>; }) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [search, setSearch] = useState<SearchResult | null>(null);
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requestSearch = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null);
    try { const result = await api.searchSatellite(tenantId, propertyId, `${start}T00:00:00Z`, `${end}T23:59:59Z`); setSearch(result); await onChanged(); }
    catch { setMessage("SOURCE_UNAVAILABLE — a busca não foi concluída."); }
    finally { setBusy(false); }
  };
  const createJob = async () => {
    if (!search?.search.selected_scene_id) return; setBusy(true); setMessage(null);
    try { setJob(await api.createNdviJob(tenantId, propertyId, search.search.id)); }
    catch { setMessage("DADO_INSUFICIENTE — não foi possível criar um job para a cena selecionada."); }
    finally { setBusy(false); }
  };
  const runJob = async () => {
    if (!job) return; setBusy(true); setMessage(null);
    try { const result = await api.runJob(tenantId, job.id); setJob(result.job); await onChanged(); }
    catch { setMessage("FAILED — a execução do job não foi concluída. Consulte o failure code persistido."); }
    finally { setBusy(false); }
  };
  const candidateRows = search?.candidates.map(candidate => {
    const scene = scenes.find(item => item.id === candidate.scene_id);
    return <li key={candidate.scene_id}><strong>{scene?.scene_id ?? candidate.scene_id}</strong><br />{scene?.acquisition_datetime ?? "UNKNOWN"} · nuvens {scene?.cloud_cover ?? "UNKNOWN"}<br /><Status value={candidate.selected ? "SELECTED" : candidate.rejection_reason ?? "AVAILABLE"} /></li>;
  });
  return <section className="operations"><h2>Cenas e processamento</h2><p>Busca oficial CDSE STAC. Datas são obrigatórias e nenhum metadado ausente é preenchido.</p><form onSubmit={requestSearch}><label>Início<input aria-label="Início da busca" type="date" value={start} onChange={event => setStart(event.target.value)} required /></label><label>Fim<input aria-label="Fim da busca" type="date" value={end} onChange={event => setEnd(event.target.value)} required /></label><button type="submit" disabled={busy}>Buscar Sentinel-2</button></form>{message && <p role="alert">{message}</p>}{search && <><p><Status value={search.search.status} /> · {search.search.candidate_count} candidatas · evidências {search.evidence_ids.length}</p><ul className="candidate-list">{candidateRows}</ul>{search.search.selected_scene_id ? <button type="button" onClick={createJob} disabled={busy}>Solicitar NDVI da cena selecionada</button> : <p>DADO_INSUFICIENTE — a política não selecionou uma cena válida.</p>}</>}{job && <div className="job"><h3>Job NDVI</h3><p><Status value={presentationStatus(job.status)} /> · {job.id}</p>{job.failure_reason && <p>failure_code: {job.failure_reason}</p>}{job.status === "PENDING" && <button type="button" onClick={runJob} disabled={busy}>Executar job</button>}{job.status === "SUCCEEDED" && <p>Produto disponível: {job.output_product_id ?? "UNKNOWN"}</p>}</div>}</section>;
}
