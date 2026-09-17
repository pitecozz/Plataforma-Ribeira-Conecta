import { useEffect, useRef } from "react";
import type { Geometry } from "geojson";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { transformMapRequest } from "./tileAuth";

interface Props {
  aoi: Geometry | null;
  apiBaseUrl: string;
  tileUrl: string | null;
  ndviEnabled: boolean;
  token: string;
}
const sourceId = "property-aoi";

export function MapCanvas({ aoi, apiBaseUrl, tileUrl, ndviEnabled, token }: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  useEffect(() => {
    if (!element.current || map.current) return;
    map.current = new maplibregl.Map({
      container: element.current,
      style: import.meta.env.VITE_MAP_STYLE_URL || "https://demotiles.maplibre.org/style.json",
      center: [-47, -24], zoom: 4,
      transformRequest: (url: string) => transformMapRequest(url, apiBaseUrl, token),
    });
    return () => { map.current?.remove(); map.current = null; };
  }, [apiBaseUrl, token]);
  useEffect(() => {
    const active = map.current;
    if (!active || !aoi) return;
    const update = () => {
      if (active.getSource(sourceId)) active.removeLayer("property-outline");
      if (active.getSource(sourceId)) active.removeSource(sourceId);
      active.addSource(sourceId, { type: "geojson", data: { type: "Feature", properties: {}, geometry: aoi } });
      active.addLayer({ id: "property-outline", type: "line", source: sourceId, paint: { "line-color": "#0f766e", "line-width": 3 } });
      const bounds = new maplibregl.LngLatBounds();
      const visit = (coordinates: unknown): void => { if (Array.isArray(coordinates) && typeof coordinates[0] === "number") bounds.extend(coordinates as [number, number]); else if (Array.isArray(coordinates)) coordinates.forEach(visit); };
      visit("coordinates" in aoi ? aoi.coordinates : aoi.geometries);
      if (!bounds.isEmpty()) active.fitBounds(bounds, { padding: 48, maxZoom: 15 });
    };
    if (active.isStyleLoaded()) update(); else active.once("load", update);
  }, [aoi]);
  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const update = () => {
      if (active.getLayer("ndvi-raster")) active.removeLayer("ndvi-raster");
      if (active.getSource("ndvi-raster")) active.removeSource("ndvi-raster");
      if (tileUrl && ndviEnabled) {
        active.addSource("ndvi-raster", { type: "raster", tiles: [tileUrl], tileSize: 256 });
        active.addLayer({ id: "ndvi-raster", type: "raster", source: "ndvi-raster", paint: { "raster-opacity": 0.72 } }, "property-outline");
      }
    };
    if (active.isStyleLoaded()) update(); else active.once("load", update);
  }, [tileUrl, ndviEnabled]);
  return <div className="map-canvas" ref={element} aria-label="Mapa da propriedade" />;
}
