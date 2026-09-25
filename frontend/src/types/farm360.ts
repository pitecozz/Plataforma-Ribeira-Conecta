import type { Geometry } from "geojson";

export type DataStatus =
  "READY" | "UNKNOWN" | "DADO_INSUFICIENTE" | "SOURCE_UNAVAILABLE";

export interface PropertyRecord {
  id: string;
  name: string;
  tenant_id: string;
  geometry_geojson: Geometry | null;
  geometry_crs: string | null;
  boundary_source: string | null;
  boundary_checksum?: string | null;
  area_hectares: string | null;
  perimeter_metres?: string | null;
  centroid?: { longitude: number; latitude: number } | null;
  bbox?: number[] | null;
  boundary_vertex_count?: number | null;
  classification: string;
  created_at: string;
  updated_at?: string | null;
  data_status: DataStatus;
}
export interface DigitalTwinAsset {
  id: string;
  tenant_id: string;
  asset_type: string;
  name: string;
  serial_number: string | null;
  status: string;
  property_id: string | null;
  site_id: string | null;
  classification: string;
  geometry_geojson: Geometry | null;
  geometry_crs: string | null;
  source_reference: string | null;
  observed_at: string | null;
  context: Record<string, unknown>;
  evidence_id?: string | null;
}

export interface AssetCreate {
  asset_type: string;
  name: string;
  serial_number?: string | null;
  status: string;
  property_id: string;
  geometry?: Geometry | null;
  geometry_crs?: "EPSG:4326" | null;
  source_reference: string;
  observed_at: string;
  context: Record<string, unknown>;
  classification: "MANUAL_CONFIRMED";
}

/**
 * Source-backed operational field/talhão context. This is deliberately not a
 * legal boundary, crop declaration, soil observation, or agronomic result.
 */
export interface FieldContext {
  id: string;
  tenant_id: string;
  property_id: string;
  name: string;
  status: string;
  geometry_geojson: Geometry;
  geometry_crs: string;
  boundary_version: number;
  boundary_checksum: string;
  source_reference: string;
  observed_at: string;
  classification: string;
  created_at: string;
  evidence_id?: string | null;
}

export interface FieldContextCreate {
  name: string;
  status: string;
  geometry_geojson: Geometry;
  geometry_crs: "EPSG:4326";
  source_reference: string;
  observed_at: string;
  classification: "MANUAL_CONFIRMED";
}

export interface FieldBoundaryCorrectionCreate {
  expected_boundary_version: number;
  expected_boundary_checksum: string;
  geometry_geojson: Geometry;
  geometry_crs: "EPSG:4326";
  source_reference: string;
  observed_at: string;
  classification: "MANUAL_CONFIRMED";
  reason: string;
}

export interface ActionOutcomeCreate {
  outcome_detail: string;
  outcome_classification: string;
  evidence_ids: string[];
  completed_at: string;
}

export type PilotFeedbackType =
  | "BUG"
  | "CONFUSING"
  | "INCORRECT_DATA"
  | "MISSING_FEATURE"
  | "SUGGESTION"
  | "USEFUL";
export interface PilotFeedback {
  id: string;
  tenant_id: string;
  property_id: string | null;
  submitted_by: string;
  feedback_type: PilotFeedbackType;
  page: string;
  feature_id: string;
  message: string;
  created_at: string;
}
export interface PropertyDecision {
  id: string;
  property_id: string;
  subject_asset_id?: string | null;
  conclusion: string;
  classification: string;
  status: string;
  evidence_ids: string[];
  rule_id: string | null;
  rule_version: number | null;
  limitations: string[];
  missing_data: string[];
  conflicts: Array<Record<string, unknown>>;
  recommended_action: Record<string, unknown> | null;
  created_at: string;
  action: {
    id: string;
    status: string;
    completed_at: string | null;
    completed_by: string | null;
    outcome_detail: string | null;
    outcome_classification: string | null;
    outcome_evidence_ids: string[];
  } | null;
}
export interface PortfolioProperty extends PropertyRecord {
  latest_scene_at: string | null;
  latest_ndvi_at: string | null;
  latest_ndvi_id: string | null;
  provenance_available: boolean;
  jobs: Record<string, number>;
}

export interface SatelliteAsset {
  id: string;
  asset_key: string;
  title: string | null;
  checksum: string | null;
  download_status: string;
  roles?: string[];
  bytes_downloaded?: number | null;
}
export interface Scene {
  id: string;
  property_id: string;
  provider: string;
  collection: string;
  scene_id: string;
  acquisition_datetime: string;
  cloud_cover: string | null;
  checksum: string;
  source_status: string;
  assets: SatelliteAsset[];
}
export interface NdviProduct {
  id: string;
  property_id: string;
  scene_id: string;
  processing_job_id: string;
  product_type: string;
  classification: string;
  statistics: {
    minimum: string | null;
    maximum: string | null;
    mean: string | null;
    median: string | null;
    valid_count: number;
    nodata_count: number;
    coverage_percentage: string | null;
  };
  checksum: string | null;
  generated_at: string;
  processing_status: string;
  algorithm_id: string;
  algorithm_version: string;
  formula: string;
  input_asset_keys: string[];
  limitations: string[];
  quality: string[];
}
export interface TimelineItem {
  scene_internal_id: string;
  scene_id: string;
  provider: string;
  collection: string;
  acquisition_datetime: string;
  cloud_cover: string | null;
  derived_product: NdviProduct;
  provenance_available: boolean;
}
export interface TemporalDeltaEvaluation {
  decision: {
    id: string;
    status: string;
    conclusion: string;
    evidence_ids: string[];
    rule_id: string | null;
    rule_version: number | null;
  };
  alert: { id: string; severity: string; status: string } | null;
  action: { id: string; action_type: string; status: string } | null;
}
export interface TemporalComparison {
  property_id: string;
  field_id: string | null;
  status: "READY" | "DADO_INSUFICIENTE" | "INCONCLUSIVE";
  baseline: NdviProduct;
  target: NdviProduct;
  comparison: {
    delta_mean: string | null;
    comparable_valid_pixels: number | null;
    comparable_coverage_percentage: string | null;
    classification:
      "DERIVED_AGGREGATE" | "PIXEL_ALIGNED_DELTA" | "INCONCLUSIVE";
    delta_product_id: string | null;
    delta_minimum: string | null;
    delta_maximum: string | null;
    delta_median: string | null;
    quality_mask_policy: Array<Record<string, unknown> | null> | null;
    alignment_summary: Record<string, unknown> | null;
    limitations: string[];
  };
}
export interface PropertyCreate {
  name: string;
  geometry_geojson: Geometry;
  geometry_crs: string;
  boundary_source: string;
  classification: "MANUAL_CONFIRMED" | "UNKNOWN";
}
export interface SearchResult {
  search: {
    id: string;
    status: string;
    selected_scene_id: string | null;
    candidate_count: number;
  };
  candidates: Array<{
    scene_id: string;
    selected: boolean;
    rejection_reason: string | null;
    rank: number;
  }>;
  evidence_ids: string[];
}
export interface ProcessingJob {
  id: string;
  job_type: string;
  status:
    "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "BLOCKED" | "CANCELLED";
  failure_code: string | null;
  failure_reason: string | null;
  output_product_id: string | null;
  attempt: number;
  max_attempts: number;
  heartbeat_at: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export interface BoundaryImport {
  id: string;
  tenant_id: string;
  property_id: string;
  original_filename: string;
  original_format: "GEOJSON" | "KML" | "KMZ";
  file_size_bytes: number;
  file_sha256: string;
  original_crs: string | null;
  detected_crs: string | null;
  target_crs: string | null;
  geometry_checksum: string | null;
  geometry_geojson?: Geometry | null;
  boundary_source: string;
  classification: string;
  warnings: string[];
  status: "NEEDS_REVIEW" | "APPROVED" | "REJECTED" | "FAILED";
  created_by: string;
  expected_property_checksum: string | null;
  created_at: string;
  reviewed_by: string | null;
  review_reason: string | null;
  approved_boundary_version: number | null;
  reviewed_at: string | null;
}
export interface BoundaryImportPreview {
  import: BoundaryImport;
  current_boundary_checksum: string | null;
  current_area_hectares: string | null;
  imported_area_hectares: string | null;
  absolute_area_delta_hectares: string | null;
  percentage_area_delta: string | null;
  current_geometry: Geometry | null;
  imported_geometry: Geometry | null;
}
export interface Provenance {
  product: NdviProduct;
  processing_job: {
    id: string | null;
    status: string;
    algorithm_id: string | null;
    algorithm_version: string | null;
    created_at: string | null;
    started_at: string | null;
    finished_at: string | null;
  };
  assets: SatelliteAsset[];
  scene: Scene | null;
  provider: { id: string; collection: string; catalog_source: string };
  evidence: Array<{
    id: string;
    evidence_type: string;
    reference_id: string;
    classification: string;
    observed_at: string | null;
    transformation: string | null;
    limitations: string[];
    created_at: string;
  }>;
  upstreams?: Array<{
    relationship: string;
    product: NdviProduct;
    scene: Scene | null;
    assets: SatelliteAsset[];
    evidence: unknown;
  }>;
}
