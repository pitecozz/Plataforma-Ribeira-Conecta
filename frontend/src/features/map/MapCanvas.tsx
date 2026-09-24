import { useEffect, useRef, useState } from "react";
import type { Geometry } from "geojson";
import * as maplibregl from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./MapCanvas.css";
import { assetMarkerSymbol, boundsForGeometry } from "./mapPresentation";
import { transformMapRequest } from "./tileAuth";
import type { DigitalTwinAsset } from "../../types/farm360";

interface Props {
  aoi: Geometry | null;
  assets?: DigitalTwinAsset[];
  selectedAssetId?: string | null;
  onAssetSelected?: (assetId: string) => void;
  recenterRequest?: number;
  apiBaseUrl: string;
  tileUrl: string | null;
  deltaTileUrl: string | null;
  ndviEnabled: boolean;
  deltaEnabled: boolean;
  token: string;
}

const sourceId = "property-aoi";
const assetSourceId = "property-assets";
maplibregl.setWorkerUrl(maplibreWorkerUrl);
const defaultBasemapStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "neutral-background", type: "background", paint: { "background-color": "#e8f0eb" } }],
};

function configuredBasemapStyle(): string | maplibregl.StyleSpecification {
  const configuredStyle = import.meta.env.VITE_RIBEIRA_BASEMAP_STYLE_URL || import.meta.env.VITE_MAP_STYLE_URL;
  if (configuredStyle) return configuredStyle;
  const cartoKey = import.meta.env.VITE_RIBEIRA_CARTO_BASEMAP_API_KEY;
  if (!cartoKey) return defaultBasemapStyle;
  return {
    version: 8,
    sources: {
      "carto-visual": {
        type: "raster",
        tiles: [`https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png?api_key=${encodeURIComponent(cartoKey)}`],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors © CARTO",
      },
    },
    layers: [{ id: "carto-visual", type: "raster", source: "carto-visual" }],
  };
}

function pointCoordinates(asset: DigitalTwinAsset): [number, number] | null {
  if (!asset.geometry_geojson) return null;
  if (asset.geometry_geojson.type === "Point") {
    const [longitude, latitude] = asset.geometry_geojson.coordinates;
    return typeof longitude === "number" && typeof latitude === "number"
      ? [longitude, latitude]
      : null;
  }
  const bounds = boundsForGeometry(asset.geometry_geojson);
  return bounds ? [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2] : null;
}

type PositionedAsset = {
  asset: DigitalTwinAsset;
  coordinates: [number, number];
  point: maplibregl.Point;
};

type MarkerGroup = {
  coordinates: [number, number];
  assets: PositionedAsset[];
};

// This is a display-only grouping threshold.  It never adjusts persisted
// coordinates: when points resolve at the current zoom they become separate
// markers again.
const overlapDistancePixels = 22;

function groupVisibleAssets(
  active: maplibregl.Map,
  assets: DigitalTwinAsset[],
): MarkerGroup[] {
  const positioned: PositionedAsset[] = assets.flatMap((asset) => {
    const coordinates = pointCoordinates(asset);
    return coordinates ? [{ asset, coordinates, point: active.project(coordinates) }] : [];
  });
  const groups: MarkerGroup[] = [];
  for (const item of positioned) {
    const existing = groups.find((group) => {
      const anchor = group.assets[0]?.point;
      return anchor ? anchor.dist(item.point) <= overlapDistancePixels : false;
    });
    if (existing) existing.assets.push(item);
    else groups.push({ coordinates: item.coordinates, assets: [item] });
  }
  return groups;
}

function overlapPopup(
  assets: PositionedAsset[],
  onSelect: (assetId: string) => void,
): HTMLElement {
  const content = document.createElement("div");
  content.className = "asset-overlap-popup";
  const title = document.createElement("strong");
  title.textContent = `${assets.length} ativos nesta localização`;
  content.append(title);
  const list = document.createElement("ul");
  for (const { asset } of assets) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = asset.name;
    button.addEventListener("click", () => onSelect(asset.id));
    item.append(button);
    list.append(item);
  }
  content.append(list);
  return content;
}

export function MapCanvas({
  aoi,
  assets = [],
  selectedAssetId,
  onAssetSelected,
  recenterRequest = 0,
  apiBaseUrl,
  tileUrl,
  deltaTileUrl,
  ndviEnabled,
  deltaEnabled,
  token,
}: Props) {
  const externalBasemapConfigured = Boolean(
    import.meta.env.VITE_RIBEIRA_BASEMAP_STYLE_URL ||
      import.meta.env.VITE_MAP_STYLE_URL ||
      import.meta.env.VITE_RIBEIRA_CARTO_BASEMAP_API_KEY,
  );
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const onAssetSelectedRef = useRef(onAssetSelected);
  const fitPropertyRef = useRef<(() => void) | null>(null);
  const assetClickAttached = useRef(false);
  const [markerLayoutVersion, setMarkerLayoutVersion] = useState(0);

  useEffect(() => {
    onAssetSelectedRef.current = onAssetSelected;
  }, [onAssetSelected]);

  useEffect(() => {
    if (!element.current || map.current) return;
    const active = new maplibregl.Map({
      container: element.current,
      style: configuredBasemapStyle(),
      center: [-47, -24],
      zoom: 4,
      transformRequest: (url: string) =>
        transformMapRequest(url, apiBaseUrl, token),
    });
    active.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    active.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
    active.on("error", (event) => {
      element.current?.setAttribute("data-map-error", event.error.message);
    });
    active.on("style.load", () => {
      element.current?.setAttribute("data-map-style-loaded", "true");
    });
    active.on("moveend", () => setMarkerLayoutVersion((value) => value + 1));
    map.current = active;

    return () => {
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      active.remove();
      map.current = null;
    };
  }, [apiBaseUrl, token]);

  useEffect(() => {
    const active = map.current;
    if (!active || !aoi) return;
    const bounds = boundsForGeometry(aoi);
    const fitProperty = () => {
      if (!bounds) return;
      active.fitBounds(bounds, { padding: 56, maxZoom: 16, duration: 650 });
    };
    fitPropertyRef.current = fitProperty;

    const update = () => {
      if (active.getLayer("property-outline")) active.removeLayer("property-outline");
      if (active.getLayer("property-outline-halo")) active.removeLayer("property-outline-halo");
      if (active.getLayer("property-fill")) active.removeLayer("property-fill");
      if (active.getSource(sourceId)) active.removeSource(sourceId);
      active.addSource(sourceId, {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: aoi },
      });
      active.addLayer({
        id: "property-fill",
        type: "fill",
        source: sourceId,
        paint: { "fill-color": "#22c55e", "fill-opacity": 0.28 },
      });
      active.addLayer({
        id: "property-outline-halo",
        type: "line",
        source: sourceId,
        paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.92 },
      });
      active.addLayer({
        id: "property-outline",
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#065f46",
          "line-width": 4.5,
          "line-opacity": 0.96,
        },
      });
      fitProperty();
      const currentBounds = active.getBounds();
      element.current?.setAttribute("data-map-bounds", currentBounds.toArray().flat().join(","));
      element.current?.setAttribute("data-map-zoom", String(active.getZoom()));
    };
    if (active.isStyleLoaded()) update();
    active.on("style.load", update);
    return () => {
      active.off("style.load", update);
    };
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
            properties: { id: asset.id, name: asset.name, asset_type: asset.asset_type },
            geometry: asset.geometry_geojson,
          })),
        },
      });
      const before = active.getLayer("property-outline") ? "property-outline" : undefined;
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
            "circle-radius": 7,
            "circle-stroke-color": "#78350f",
            "circle-stroke-width": 2,
          },
        },
        before,
      );
      if (!assetClickAttached.current) {
        active.on("click", "asset-points", (event) => {
          const assetId = event.features?.[0]?.properties?.id;
          if (typeof assetId === "string") onAssetSelectedRef.current?.(assetId);
        });
        active.on("mouseenter", "asset-points", () => {
          active.getCanvas().style.cursor = "pointer";
        });
        active.on("mouseleave", "asset-points", () => {
          active.getCanvas().style.cursor = "";
        });
        assetClickAttached.current = true;
      }
    };
    if (active.isStyleLoaded()) update();
    active.on("style.load", update);
    return () => {
      active.off("style.load", update);
    };
  }, [assets]);

  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const created = groupVisibleAssets(active, assets).map((group) => {
      const grouped = group.assets.length > 1;
      const selected = group.assets.some(({ asset }) => selectedAssetId === asset.id);
      const markerElement = document.createElement("button");
      markerElement.type = "button";
      markerElement.className = `property-asset-marker${grouped ? " asset-overlap-marker" : ""}${selected ? " selected" : ""}`;
      markerElement.setAttribute(
        "aria-label",
        grouped
          ? `Abrir ${group.assets.length} ativos próximos`
          : `Abrir ativo: ${group.assets[0]?.asset.name ?? ""}`,
      );
      markerElement.setAttribute("data-asset-ids", group.assets.map(({ asset }) => asset.id).join(","));
      markerElement.title = grouped
        ? `${group.assets.length} ativos próximos — clique para ver a lista`
        : group.assets[0]?.asset.name ?? "";
      markerElement.textContent = grouped
        ? String(group.assets.length)
        : assetMarkerSymbol(group.assets[0]?.asset.asset_type ?? "");
      const popup = new maplibregl.Popup({ offset: 20 });
      if (grouped) {
        markerElement.addEventListener("click", () => {
          popup.setDOMContent(overlapPopup(group.assets, (assetId) => onAssetSelectedRef.current?.(assetId)));
        });
      } else {
        const asset = group.assets[0]?.asset;
        markerElement.addEventListener("click", () => asset && onAssetSelectedRef.current?.(asset.id));
        popup.setText(asset?.name ?? "Ativo");
      }
      return new maplibregl.Marker({ element: markerElement, anchor: "bottom" })
        .setLngLat(group.coordinates)
        .setPopup(popup)
        .addTo(active);
    });
    markers.current = created;
    return () => {
      created.forEach((marker) => marker.remove());
      if (markers.current === created) markers.current = [];
    };
  }, [assets, markerLayoutVersion, selectedAssetId]);

  useEffect(() => {
    const active = map.current;
    const asset = assets.find((item) => item.id === selectedAssetId);
    const coordinates = asset ? pointCoordinates(asset) : null;
    if (!active || !coordinates) return;
    active.easeTo({ center: coordinates, zoom: Math.max(active.getZoom(), 18), duration: 450 });
  }, [assets, selectedAssetId]);

  useEffect(() => {
    if (recenterRequest > 0) fitPropertyRef.current?.();
  }, [recenterRequest]);

  useEffect(() => {
    const active = map.current;
    if (!active) return;
    const update = () => {
      if (active.getLayer("ndvi-raster")) active.removeLayer("ndvi-raster");
      if (active.getSource("ndvi-raster")) active.removeSource("ndvi-raster");
      if (tileUrl && ndviEnabled) {
        active.addSource("ndvi-raster", { type: "raster", tiles: [tileUrl], tileSize: 256 });
        active.addLayer(
          { id: "ndvi-raster", type: "raster", source: "ndvi-raster", paint: { "raster-opacity": 0.72 } },
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
        active.addSource("delta-raster", { type: "raster", tiles: [deltaTileUrl], tileSize: 256 });
        active.addLayer(
          { id: "delta-raster", type: "raster", source: "delta-raster", paint: { "raster-opacity": 0.78 } },
          "property-outline",
        );
      }
    };
    if (active.isStyleLoaded()) update();
    else active.once("load", update);
  }, [deltaTileUrl, deltaEnabled]);

  return (
    <div className="map-frame">
      <div className="map-canvas" ref={element} aria-label="Mapa da propriedade" />
      {!externalBasemapConfigured && <p className="map-basemap-unavailable">Mapa base não configurado. O limite e os ativos cadastrados continuam disponíveis neste mapa.</p>}
      <button className="map-recenter" type="button" onClick={() => fitPropertyRef.current?.()}>
        Centralizar sítio
      </button>
    </div>
  );
}
