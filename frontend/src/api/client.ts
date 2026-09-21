import type {
  BoundaryImport,
  BoundaryImportPreview,
  DigitalTwinAsset,
  NdviProduct,
  PilotFeedback,
  PilotFeedbackType,
  PropertyDecision,
  PortfolioProperty,
  ProcessingJob,
  PropertyCreate,
  PropertyRecord,
  Provenance,
  Scene,
  SearchResult,
  TemporalComparison,
  TimelineItem,
} from "../types/farm360";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export class Farm360Api {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
  ) {}

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        `Request failed (${response.status})`,
      );
    return response.json() as Promise<T>;
  }
  private async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        `Request failed (${response.status})`,
      );
    return response.json() as Promise<T>;
  }
  private async rawPost<T>(
    path: string,
    body: Blob,
    headers: Record<string, string>,
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.token}`, ...headers },
      body,
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        `Request failed (${response.status})`,
      );
    return response.json() as Promise<T>;
  }

  properties(tenantId: string) {
    return this.get<{ items: PropertyRecord[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties`,
    );
  }
  portfolio(tenantId: string) {
    return this.get<{ items: PortfolioProperty[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/portfolio`,
    );
  }
  createProperty(tenantId: string, payload: PropertyCreate) {
    return this.post<PropertyRecord>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties`,
      payload,
    );
  }
  property(tenantId: string, propertyId: string) {
    return this.get<PropertyRecord>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}`,
    );
  }
  assets(tenantId: string, propertyId: string) {
    return this.get<{ property_id: string; items: DigitalTwinAsset[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/assets`,
    );
  }
  submitPilotFeedback(
    tenantId: string,
    payload: {
      feedback_type: PilotFeedbackType;
      page: string;
      feature_id: string;
      message: string;
      property_id?: string;
    },
  ) {
    return this.post<PilotFeedback>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/pilot-feedback`,
      payload,
    );
  }
  decisions(tenantId: string, propertyId: string) {
    return this.get<{ property_id: string; items: PropertyDecision[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/decisions`,
    );
  }
  scenes(tenantId: string, propertyId: string) {
    return this.get<{ items: Scene[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/scenes`,
    );
  }
  products(tenantId: string, propertyId: string) {
    return this.get<{ items: NdviProduct[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/derived-products`,
    );
  }
  timeline(tenantId: string, propertyId: string) {
    return this.get<{
      property_id: string;
      order: "acquisition_datetime_asc";
      items: TimelineItem[];
    }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/timeline`,
    );
  }
  comparison(
    tenantId: string,
    propertyId: string,
    baselineProductId: string,
    targetProductId: string,
  ) {
    return this.get<TemporalComparison>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/temporal-comparison?baseline_product_id=${encodeURIComponent(baselineProductId)}&target_product_id=${encodeURIComponent(targetProductId)}`,
    );
  }
  provenance(tenantId: string, productId: string) {
    return this.get<Provenance>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/derived-products/${encodeURIComponent(productId)}/provenance`,
    );
  }
  searchSatellite(
    tenantId: string,
    propertyId: string,
    datetimeStart: string,
    datetimeEnd: string,
  ) {
    return this.post<SearchResult>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/satellite-searches`,
      { datetime_start: datetimeStart, datetime_end: datetimeEnd },
    );
  }
  createNdviJob(tenantId: string, propertyId: string, searchId: string) {
    return this.post<ProcessingJob>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/ndvi-jobs`,
      { search_id: searchId },
    );
  }
  job(tenantId: string, jobId: string) {
    return this.get<ProcessingJob>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/processing-jobs/${encodeURIComponent(jobId)}`,
    );
  }
  retryJob(tenantId: string, jobId: string) {
    return this.post<ProcessingJob>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/processing-jobs/${encodeURIComponent(jobId)}/retry`,
    );
  }
  boundaryImports(tenantId: string, propertyId: string) {
    return this.get<{ items: BoundaryImport[] }>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/boundary-imports`,
    );
  }
  uploadBoundaryImport(
    tenantId: string,
    propertyId: string,
    file: File,
    source: string,
    classification: string,
    crs: string,
  ) {
    return this.rawPost<BoundaryImport>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/boundary-imports`,
      file,
      {
        "Content-Type": "application/geo+json",
        "X-Boundary-Filename": file.name,
        "X-Boundary-Source": source,
        "X-Boundary-Classification": classification,
        "X-Boundary-CRS": crs,
      },
    );
  }
  boundaryImportPreview(tenantId: string, importId: string) {
    return this.get<BoundaryImportPreview>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/boundary-imports/${encodeURIComponent(importId)}/preview`,
    );
  }
  approveBoundaryImport(
    tenantId: string,
    importId: string,
    reviewReason: string,
    expectedPropertyChecksum: string,
  ) {
    return this.post<BoundaryImport>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/boundary-imports/${encodeURIComponent(importId)}/approve`,
      {
        review_reason: reviewReason,
        expected_property_checksum: expectedPropertyChecksum,
      },
    );
  }
  rejectBoundaryImport(
    tenantId: string,
    importId: string,
    reviewReason: string,
  ) {
    return this.post<BoundaryImport>(
      `/v1/tenants/${encodeURIComponent(tenantId)}/boundary-imports/${encodeURIComponent(importId)}/reject`,
      { review_reason: reviewReason },
    );
  }
  tileTemplate(tenantId: string, productId: string) {
    return `${this.baseUrl}/v1/tenants/${encodeURIComponent(tenantId)}/derived-products/${encodeURIComponent(productId)}/tiles/{z}/{x}/{y}`;
  }
}
