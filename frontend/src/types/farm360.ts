import type { Geometry } from "geojson";

export type DataStatus = "READY" | "UNKNOWN" | "DADO_INSUFICIENTE" | "SOURCE_UNAVAILABLE";

export interface PropertyRecord {
  id: string;
  name: string;
  tenant_id: string;
  geometry_geojson: Geometry | null;
  geometry_crs: string | null;
  area_hectares: string | null;
  classification: string;
  created_at: string;
  data_status: DataStatus;
}

export interface SatelliteAsset { id: string; asset_key: string; title: string | null; checksum: string | null; download_status: string; roles?: string[]; bytes_downloaded?: number | null; }
export interface Scene { id: string; property_id: string; provider: string; collection: string; scene_id: string; acquisition_datetime: string; cloud_cover: string | null; checksum: string; source_status: string; assets: SatelliteAsset[]; }
export interface NdviProduct { id: string; property_id: string; scene_id: string; processing_job_id: string; product_type: string; classification: string; statistics: { minimum: string | null; maximum: string | null; mean: string | null; median: string | null; valid_count: number; nodata_count: number; coverage_percentage: string | null; }; checksum: string | null; generated_at: string; processing_status: string; algorithm_id: string; algorithm_version: string; formula: string; input_asset_keys: string[]; limitations: string[]; quality: string[]; }
export interface TimelineItem { scene_internal_id: string; scene_id: string; provider: string; collection: string; acquisition_datetime: string; cloud_cover: string | null; derived_product: NdviProduct; provenance_available: boolean; }
export interface TemporalComparison { property_id: string; status: "READY" | "DADO_INSUFICIENTE" | "INCONCLUSIVE"; baseline: NdviProduct; target: NdviProduct; comparison: { delta_mean: string | null; comparable_valid_pixels: number | null; comparable_coverage_percentage: string | null; classification: "DERIVED_AGGREGATE" | "PIXEL_ALIGNED_DELTA" | "INCONCLUSIVE"; delta_product_id: string | null; delta_minimum: string | null; delta_maximum: string | null; delta_median: string | null; quality_mask_policy: Array<Record<string, unknown> | null> | null; alignment_summary: Record<string, unknown> | null; limitations: string[]; }; }
export interface Provenance { product: NdviProduct; processing_job: { id: string | null; status: string; algorithm_id: string | null; algorithm_version: string | null; created_at: string | null; started_at: string | null; finished_at: string | null; }; assets: SatelliteAsset[]; scene: Scene | null; provider: { id: string; collection: string; catalog_source: string }; evidence: Array<{ id: string; evidence_type: string; reference_id: string; classification: string; observed_at: string | null; transformation: string | null; limitations: string[]; created_at: string }>; upstreams?: Array<{ relationship: string; product: NdviProduct; scene: Scene | null; assets: SatelliteAsset[]; evidence: unknown }>; }
