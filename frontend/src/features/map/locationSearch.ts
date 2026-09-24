export type LocationSearchResult = { longitude: number; latitude: number; label: string; source: "COORDINATES" };

/** Parses an explicit longitude/latitude pair; provider geocoders remain adapters. */
export function parseCoordinates(query: string): LocationSearchResult | null {
  const match = query.trim().match(/^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!match) return null;
  const first = Number(match[1]); const second = Number(match[2]);
  if (!Number.isFinite(first) || !Number.isFinite(second)) return null;
  const [longitude, latitude] = Math.abs(first) <= 90 && Math.abs(second) > 90 ? [second, first] : [first, second];
  if (longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) return null;
  return { longitude, latitude, label: `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`, source: "COORDINATES" };
}
