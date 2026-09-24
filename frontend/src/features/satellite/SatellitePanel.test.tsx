import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SatellitePanel } from "./SatellitePanel";
import type { Scene } from "../../types/farm360";

const scene: Scene = {
  id: "scene-1",
  property_id: "property-1",
  provider: "COPERNICUS_CDSE",
  collection: "sentinel-2-l2a",
  scene_id: "S2_TEST_001",
  acquisition_datetime: "2025-12-31T13:22:51Z",
  cloud_cover: "22.41",
  checksum: "checksum",
  source_status: "COMPLETED",
  assets: [],
};

describe("SatellitePanel", () => {
  it("shows a persisted catalog scene without claiming that an NDVI product exists", () => {
    render(<SatellitePanel scene={null} scenes={[scene]} />);
    expect(screen.getByText(/cena catalogada para esta propriedade/i)).toBeInTheDocument();
    expect(screen.getByText("22.41%")).toBeInTheDocument();
    expect(screen.getByText("Metadados da cena catalogados")).toBeInTheDocument();
  });
});
