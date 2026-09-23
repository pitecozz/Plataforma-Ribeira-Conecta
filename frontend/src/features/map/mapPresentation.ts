import type { Geometry } from "geojson";

type Bounds = [number, number, number, number];

export function boundsForGeometry(geometry: Geometry): Bounds | null {
  let west = Number.POSITIVE_INFINITY;
  let south = Number.POSITIVE_INFINITY;
  let east = Number.NEGATIVE_INFINITY;
  let north = Number.NEGATIVE_INFINITY;

  const visitCoordinates = (coordinates: unknown): void => {
    if (
      Array.isArray(coordinates) &&
      typeof coordinates[0] === "number" &&
      typeof coordinates[1] === "number"
    ) {
      const [longitude, latitude] = coordinates;
      west = Math.min(west, longitude);
      south = Math.min(south, latitude);
      east = Math.max(east, longitude);
      north = Math.max(north, latitude);
      return;
    }
    if (Array.isArray(coordinates)) coordinates.forEach(visitCoordinates);
  };

  if (geometry.type === "GeometryCollection") {
    geometry.geometries.forEach((item) => {
      const bounds = boundsForGeometry(item);
      if (!bounds) return;
      west = Math.min(west, bounds[0]);
      south = Math.min(south, bounds[1]);
      east = Math.max(east, bounds[2]);
      north = Math.max(north, bounds[3]);
    });
  } else {
    visitCoordinates(geometry.coordinates);
  }

  return Number.isFinite(west) ? [west, south, east, north] : null;
}

export function assetMarkerSymbol(assetType: string): string {
  const normalized = assetType.toLowerCase().replaceAll("_", " ");
  if (normalized.includes("camera")) return "◉";
  if (normalized.includes("shed") || normalized.includes("barrac")) return "▰";
  if (normalized.includes("house") || normalized.includes("casa")) return "⌂";
  if (normalized.includes("pump") || normalized.includes("bomba")) return "≈";
  if (normalized.includes("sensor")) return "◌";
  return "●";
}
