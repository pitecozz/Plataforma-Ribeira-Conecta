import { useEffect, useRef, useState } from "react";
import type { Farm360Api } from "../../api/client";
import type {
  ProcessingJob,
  TemporalComparison,
  TimelineItem,
} from "../../types/farm360";

interface Props {
  api: Farm360Api;
  tenantId: string;
  propertyId: string;
  items: TimelineItem[];
  selectedProductId: string | null;
  mode: "view" | "compare";
  baselineProductId: string | null;
  targetProductId: string | null;
  comparison: TemporalComparison | null;
  comparisonLoading: boolean;
  canProcess?: boolean;
  onChanged: () => Promise<void>;
  onSelectProduct: (productId: string) => void;
  onModeChange: (mode: "view" | "compare") => void;
  onBaselineChange: (productId: string) => void;
  onTargetChange: (productId: string) => void;
}

function dateLabel(item: TimelineItem) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(item.acquisition_datetime));
}

function terminal(job: ProcessingJob) {
  return ["SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"].includes(job.status);
}

export function TemporalPanel(props: Props) {
  const {
    items,
    selectedProductId,
    mode,
    baselineProductId,
    targetProductId,
    comparison,
    comparisonLoading,
    canProcess = false,
  } = props;
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const waitForJob = async (created: ProcessingJob) => {
    let current = created;
    setJob(current);
    while (!terminal(current)) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      current = await props.api.job(props.tenantId, current.id);
      if (!active.current) throw new Error("cancelled");
      setJob(current);
    }
    if (current.status !== "SUCCEEDED" || !current.output_product_id) {
      throw new Error(current.failure_code ?? current.status);
    }
    return current.output_product_id;
  };

  const ensureMasked = async (productId: string) => {
    const product = items.find(
      (item) => item.derived_product.id === productId,
    )?.derived_product;
    if (!product) throw new Error("missing product");
    if (product.product_type === "NDVI_QUALITY_MASKED") return product.id;
    return waitForJob(
      await props.api.createQualityMaskedNdviJob(
        props.tenantId,
        props.propertyId,
        product.id,
      ),
    );
  };

  const processComparison = async () => {
    if (!baselineProductId || !targetProductId) return;
    setBusy(true);
    setMessage(null);
    try {
      const baselineMaskedId = await ensureMasked(baselineProductId);
      const targetMaskedId = await ensureMasked(targetProductId);
      await waitForJob(
        await props.api.createTemporalDeltaJob(
          props.tenantId,
          props.propertyId,
          baselineMaskedId,
          targetMaskedId,
        ),
      );
      await props.onChanged();
      setMessage("Comparação temporal processada com proveniência persistida.");
    } catch (error) {
      if (active.current) {
        const reason = error instanceof Error ? error.message : "UNKNOWN";
        setMessage(`DADO_INSUFICIENTE — processamento não concluído (${reason}).`);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  };

  if (items.length === 0)
    return (
      <section>
        <h2>Linha do tempo</h2>
        <p>Sem dados disponíveis para comparação temporal.</p>
      </section>
    );
  return (
    <section className="temporal">
      <h2>Linha do tempo</h2>
      <p className="temporal-order">
        Ordem: aquisição crescente. O padrão visual é o NDVI SUCCEEDED mais
        recente.
      </p>
      <div className="timeline-items">
        {items.map((item) => (
          <button
            type="button"
            key={item.derived_product.id}
            className={selectedProductId === item.derived_product.id ? "selected" : ""}
            onClick={() => props.onSelectProduct(item.derived_product.id)}
          >
            <strong>{dateLabel(item)}</strong>
            <span>
              {item.derived_product.processing_status} · cobertura{" "}
              {item.derived_product.statistics.coverage_percentage ?? "NULL"}%
            </span>
            <span>Nuvens: {item.cloud_cover ?? "UNKNOWN"}</span>
          </button>
        ))}
      </div>
      <div className="temporal-mode">
        <button
          type="button"
          className={mode === "view" ? "selected" : ""}
          onClick={() => props.onModeChange("view")}
        >
          Visualizar
        </button>
        <button
          type="button"
          className={mode === "compare" ? "selected" : ""}
          onClick={() => props.onModeChange("compare")}
        >
          Comparar
        </button>
      </div>
      {mode === "compare" && (
        <div className="comparison-controls">
          <label>
            Base
            <select
              value={baselineProductId ?? ""}
              onChange={(event) => props.onBaselineChange(event.target.value)}
            >
              {items.map((item) => (
                <option key={item.derived_product.id} value={item.derived_product.id}>
                  {dateLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Target
            <select
              value={targetProductId ?? ""}
              onChange={(event) => props.onTargetChange(event.target.value)}
            >
              {items.map((item) => (
                <option key={item.derived_product.id} value={item.derived_product.id}>
                  {dateLabel(item)}
                </option>
              ))}
            </select>
          </label>
          {canProcess && (
            <button
              type="button"
              disabled={busy || !baselineProductId || !targetProductId || baselineProductId === targetProductId}
              onClick={() => void processComparison()}
            >
              {busy ? "Processando…" : "Gerar Δ NDVI com máscara de qualidade"}
            </button>
          )}
          {job && <p>Job {job.job_type}: {job.status}</p>}
          {message && <p role="status">{message}</p>}
          {comparisonLoading && <p>Calculando comparação…</p>}
          {!comparisonLoading && comparison && (
            <div className="comparison-result">
              <strong>{comparison.status}</strong>
              <span>
                Δ médio: {comparison.comparison.delta_mean ?? "INCONCLUSIVE"}
              </span>
              <span>
                Pixels comparáveis:{" "}
                {comparison.comparison.comparable_valid_pixels ?? "UNKNOWN"}
              </span>
              <span>
                Cobertura comparável:{" "}
                {comparison.comparison.comparable_coverage_percentage ?? "UNKNOWN"}%
              </span>
              <span>{comparison.comparison.classification}</span>
              {comparison.comparison.limitations.map((limitation) => (
                <small key={limitation}>{limitation}</small>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
