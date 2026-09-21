import { useEffect, useRef } from "react";
import type { Geometry } from "geojson";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { transformMapRequest } from "./tileAuth";
import type { DigitalTwinAsset } from "../../types/farm360";

interface Props {
  aoi: Geometry | null;
  assets?: DigitalTwinAsset[];
  onAssetSelected?: (assetId: string) => void;
  apiBaseUrl: string;
  tileUrl: string | null;
  deltaTileUrl: string | null;
  ndviEnabled: boolean;
  deltaEnabled: boolean;
  token: string;
}
const sourceId = "property-aoi";
const assetSourceId = "property-assets";

export function MapCanvas({
  aoi,
  assets = [],
  onAssetSelected,
  apiBaseUrl,
  tileUrl,
  deltaTileUrl,
  ndviEnabled,
  deltaEnabled,
  token,
}: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const onAssetSelectedRef = useRef(onAssetSelected);
  const assetClickAttached = useRef(false);
  useEffect(() => {
    onAssetSelectedRef.current = onAssetSelected;
  }, [onAssetSelected]);
  useEffect(() => {
    if (!element.current || map.current) return;
    map.current = new maplibregl.Map({
      container: element.current,
      style:
        import.meta.env.VITE_MAP_STYLE_URL ||
        "https://demotiles.maplibre.org/style.json",
      center: [-47, -24],
      zoom: 4,
      transformRequest: (url: string) =>
        transformMapRequest(url, apiBaseUrl, token),
    });
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [apiBaseUrl, token]);
  useEffect(() => {
    const active = map.current;
    if (!active || !aoi) return;
    const update = () => {
      if (active.getSource(sourceId)) active.removeLayer("property-outline");
      if (active.getSource(sourceId)) active.removeSource(sourceId);
      active.addSource(sourceId, {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: aoi },
      });
      active.addLayer({
        id: "property-outline",
        type: "line",
        source: sourceId,
        paint: { "line-color": "#0f766e", "line-width": 3 },
      });
      const bounds = new maplibregl.LngLatBounds();
      const visit = (coordinates: unknown): void => {
        if (Array.isArray(coordinates) && typeof coordinates[0] === "number")
          bounds.extend(coordinates as [number, number]);
        else if (Array.isArray(coordinates)) coordinates.forEach(visit);
      };
      visit("coordinates" in aoi ? aoi.coordinates : aoi.geometries);
      if (!bounds.isEmpty())
        active.fitBounds(bounds, { padding: 48, maxZoom: 15 });
    };
    if (active.isStyleLoaded()) update();
    else active.once("load", update);
  }, [aoi]);
  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const update = () => {
      const spatialAssets = assets.filter(
        (asset): asset is DigitalTwinAsset & { geometry_geojson: Geometry } =>
          asset.geometry_geojson !== null,
      );
      for (const layerId of ["asset-points", "asset-lines", "asset-areas"]) {
        if (active.getLayer(layerId)) active.removeLayer(layerId);
      }
      if (active.getSource(assetSourceId)) active.removeSource(assetSourceId);
      active.addSource(assetSourceId, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: spatialAssets.map((asset) => ({
            type: "Feature",
            properties: {
              id: asset.id,
              name: asset.name,
              asset_type: asset.asset_type,
            },
            geometry: asset.geometry_geojson,
          })),
        },
      });
      const before = active.getLayer("property-outline")
        ? "property-outline"
        : undefined;
      active.addLayer(
        {
          id: "asset-areas",
          type: "fill",
          source: assetSourceId,
          filter: ["==", "$type", "Polygon"],
          paint: { "fill-color": "#f59e0b", "fill-opacity": 0.24 },
        },
        before,
      );
      active.addLayer(
        {
          id: "asset-lines",
          type: "line",
          source: assetSourceId,
          filter: ["==", "$type", "LineString"],
          paint: { "line-color": "#b45309", "line-width": 3 },
        },
        before,
      );
      active.addLayer(
        {
          id: "asset-points",
          type: "circle",
          source: assetSourceId,
          filter: ["==", "$type", "Point"],
          paint: {
            "circle-color": "#f59e0b",
            "circle-radius": 6,
            "circle-stroke-color": "#78350f",
            "circle-stroke-width": 1,
          },
        },
        before,
      );
      if (!assetClickAttached.current) {
        active.on("click", "asset-points", (event) => {
          const assetId = event.features?.[0]?.properties?.id;
          if (typeof assetId === "string")
            onAssetSelectedRef.current?.(assetId);
        });
        assetClickAttached.current = true;
      }
    };
    if (active.isStyleLoaded()) update();
    else active.once("load", update);
  }, [assets]);
  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const update = () => {
      if (active.getLayer("ndvi-raster")) active.removeLayer("ndvi-raster");
      if (active.getSource("ndvi-raster")) active.removeSource("ndvi-raster");
      if (tileUrl && ndviEnabled) {
        active.addSource("ndvi-raster", {
          type: "raster",
          tiles: [tileUrl],
          tileSize: 256,
        });
        active.addLayer(
          {
            id: "ndvi-raster",
            type: "raster",
            source: "ndvi-raster",
            paint: { "raster-opacity": 0.72 },
          },
          "property-outline",
        );
      }
    };
    if (active.isStyleLoaded()) update();
    else active.once("load", update);
  }, [tileUrl, ndviEnabled]);
  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const update = () => {
      if (active.getLayer("delta-raster")) active.removeLayer("delta-raster");
      if (active.getSource("delta-raster")) active.removeSource("delta-raster");
      if (deltaTileUrl && deltaEnabled) {
        active.addSource("delta-raster", {
          type: "raster",
          tiles: [deltaTileUrl],
          tileSize: 256,
        });
        active.addLayer(
          {
            id: "delta-raster",
            type: "raster",
            source: "delta-raster",
            paint: { "raster-opacity": 0.78 },
          },
          "property-outline",
        );
      }
    };
    if (active.isStyleLoaded()) update();
    else active.once("load", update);
  }, [deltaTileUrl, deltaEnabled]);
  return (
    <div
      className="map-canvas"
      ref={element}
      aria-label="Mapa da propriedade"
    />
  );
}
