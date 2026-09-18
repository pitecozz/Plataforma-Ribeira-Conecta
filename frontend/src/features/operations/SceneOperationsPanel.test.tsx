import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SceneOperationsPanel } from "./SceneOperationsPanel";
import type { Farm360Api } from "../../api/client";
import type { Scene } from "../../types/farm360";

const queued = { id: "job-1", job_type: "NDVI", status: "QUEUED", failure_code: null, failure_reason: null, output_product_id: null, attempt: 0, max_attempts: 3, heartbeat_at: null, created_at: "2026-01-01T00:00:00Z", started_at: null, finished_at: null } as const;
const succeeded = { ...queued, status: "SUCCEEDED" as const, attempt: 1, output_product_id: "real-product" };
const scene: Scene = {
  id: "scene-1",
  property_id: "property",
  provider: "CDSE",
  collection: "sentinel-2-l2a",
  scene_id: "S2_REAL_VALIDATION",
  acquisition_datetime: "2026-01-01T00:00:00Z",
  cloud_cover: null,
  checksum: "test-checksum",
  source_status: "OFFICIAL_SOURCE",
  assets: [],
};

afterEach(() => vi.useRealTimers());

describe("SceneOperationsPanel asynchronous NDVI job", () => {
  it("enqueues quickly, polls with cleanup, and refreshes only after completion", async () => {
    vi.useFakeTimers();
    const api = {
      searchSatellite: vi.fn().mockResolvedValue({ search: { id: "search-1", status: "COMPLETED", selected_scene_id: "scene-1", candidate_count: 1 }, candidates: [{ scene_id: "scene-1", selected: true, rejection_reason: null, rank: 1 }], evidence_ids: ["evidence-1"] }),
      createNdviJob: vi.fn().mockResolvedValue(queued),
      job: vi.fn().mockResolvedValueOnce(queued).mockResolvedValueOnce(succeeded),
    } as unknown as Farm360Api;
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<SceneOperationsPanel api={api} tenantId="tenant" propertyId="property" scenes={[scene]} onChanged={onChanged} />);

    fireEvent.change(screen.getByLabelText("Início da busca"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("Fim da busca"), { target: { value: "2026-01-02" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar Sentinel-2" }));
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Enfileirar NDVI da cena selecionada" }));
    await act(async () => { await Promise.resolve(); });
    expect(api.createNdviJob).toHaveBeenCalledOnce();
    expect(screen.getByText("Na fila; a API não executa Rasterio/GDAL.")).toBeInTheDocument();
    await act(async () => { await vi.runOnlyPendingTimersAsync(); });
    expect(api.job).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Produto disponível: real-product")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(2);
  });
});
