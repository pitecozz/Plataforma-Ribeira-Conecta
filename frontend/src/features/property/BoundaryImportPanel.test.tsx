import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Farm360Api } from "../../api/client";
import type { BoundaryImport, PropertyRecord } from "../../types/farm360";
import { BoundaryImportPanel } from "./BoundaryImportPanel";

const property = {
  id: "property", tenant_id: "tenant", name: "SYNTHETIC_TEST_PROPERTY",
  geometry_geojson: null, geometry_crs: "EPSG:4326", boundary_source: "synthetic",
  boundary_checksum: "a".repeat(64), area_hectares: "1", classification: "MANUAL_CONFIRMED",
  created_at: "2026-01-01T00:00:00Z", data_status: "UNKNOWN",
} as PropertyRecord;
const imported = {
  id: "import", tenant_id: "tenant", property_id: "property", original_filename: "synthetic_test_data.geojson",
  original_format: "GEOJSON", file_size_bytes: 10, file_sha256: "f".repeat(64),
  original_crs: "EPSG:4326", detected_crs: "EPSG:4326", target_crs: "EPSG:4326",
  geometry_checksum: "g".repeat(64), boundary_source: "synthetic", classification: "MANUAL_CONFIRMED",
  warnings: [], status: "NEEDS_REVIEW", created_by: "importer", expected_property_checksum: "a".repeat(64),
  created_at: "2026-01-01T00:00:00Z", reviewed_by: null, review_reason: null, approved_boundary_version: null, reviewed_at: null,
} as BoundaryImport;

afterEach(cleanup);

describe("BoundaryImportPanel", () => {
  it("uploads explicit synthetic_test_data, previews hashes, and approves only through the API", async () => {
    const api = {
      boundaryImports: vi.fn().mockResolvedValue({ items: [] }),
      uploadBoundaryImport: vi.fn().mockResolvedValue(imported),
      boundaryImportPreview: vi.fn().mockResolvedValue({ import: imported, current_boundary_checksum: property.boundary_checksum, current_area_hectares: "1", imported_area_hectares: "2", absolute_area_delta_hectares: "1", percentage_area_delta: "100", current_geometry: null, imported_geometry: null }),
      approveBoundaryImport: vi.fn().mockResolvedValue({ ...imported, status: "APPROVED", approved_boundary_version: 2 }),
    } as unknown as Farm360Api;
    const changed = vi.fn().mockResolvedValue(undefined);
    render(<BoundaryImportPanel api={api} tenantId="tenant" property={property} onBoundaryChanged={changed} />);
    const file = new File(["{\"type\":\"Polygon\"}"], "synthetic_test_data.geojson", { type: "application/geo+json" });
    fireEvent.change(screen.getByLabelText("Arquivo GeoJSON"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Origem do import"), { target: { value: "synthetic test source" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar para revisão" }));
    expect(await screen.findByText("Preview de evidência")).toBeInTheDocument();
    expect(screen.getByText(/ffffffffffff/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Razão da revisão"), { target: { value: "synthetic review" } });
    fireEvent.click(screen.getByRole("button", { name: "Aprovar limite" }));
    await waitFor(() => expect(api.approveBoundaryImport).toHaveBeenCalledWith("tenant", "import", "synthetic review", property.boundary_checksum));
    expect(changed).toHaveBeenCalledOnce();
    expect(screen.queryByText(/local:\/\//)).not.toBeInTheDocument();
  });

  it("blocks an oversized client file before any upload", async () => {
    const api = { boundaryImports: vi.fn().mockResolvedValue({ items: [] }), uploadBoundaryImport: vi.fn() } as unknown as Farm360Api;
    render(<BoundaryImportPanel api={api} tenantId="tenant" property={property} onBoundaryChanged={vi.fn()} />);
    const file = new File([new Uint8Array(1_000_001)], "synthetic_test_data.geojson");
    fireEvent.change(screen.getByLabelText("Arquivo GeoJSON"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Origem do import"), { target: { value: "synthetic" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar para revisão" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("BOUNDARY_IMPORT_TOO_LARGE");
    expect(api.uploadBoundaryImport).not.toHaveBeenCalled();
  });
});
