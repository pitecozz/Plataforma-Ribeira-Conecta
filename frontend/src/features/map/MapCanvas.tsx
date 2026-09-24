import { useEffect, useRef, useState } from "react";
import type { Geometry } from "geojson";
import * as maplibregl from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./MapCanvas.css";
import { assetMarkerSymbol, boundsForGeometry } from "./mapPresentation";
import { runtimeBasemapStatus } from "./basemapStatus";
import { transformMapRequest } from "./tileAuth";
import { areaSquareMetres, distanceMetres, type Coordinate } from "./measurements";
import { parseCoordinates } from "./locationSearch";
import type { DigitalTwinAsset, FieldContext } from "../../types/farm360";

interface Props {
  aoi: Geometry | null;
  assets?: DigitalTwinAsset[];
  fields?: FieldContext[];
  selectedAssetId?: string | null;
  onAssetSelected?: (assetId: string) => void;
  recenterRequest?: number;
  apiBaseUrl: string;
  tileUrl: string | null;
  deltaTileUrl: string | null;
  ndviEnabled: boolean;
  deltaEnabled: boolean;
  token: string;
  onMapClick?: (coordinates: [number, number]) => void;
  selectionLocation?: [number, number] | null;
}

const sourceId = "property-aoi";
const assetSourceId = "property-assets";
const fieldSourceId = "property-fields";
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
  fields = [],
  selectedAssetId,
  onAssetSelected,
  recenterRequest = 0,
  apiBaseUrl,
  tileUrl,
  deltaTileUrl,
  ndviEnabled,
  deltaEnabled,
  token,
  onMapClick,
  selectionLocation = null,
}: Props) {
  const basemapStatus = runtimeBasemapStatus();
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const locationMarker = useRef<maplibregl.Marker | null>(null);
  const selectionMarker = useRef<maplibregl.Marker | null>(null);
  const onAssetSelectedRef = useRef(onAssetSelected);
  const onMapClickRef = useRef(onMapClick);
  const fitPropertyRef = useRef<(() => void) | null>(null);
  const assetClickAttached = useRef(false);
  const [markerLayoutVersion, setMarkerLayoutVersion] = useState(0);
  const [measurementMode, setMeasurementMode] = useState<"none" | "distance" | "area" | "coordinates">("none");
  const measurementModeRef = useRef(measurementMode);
  const [measurementPoints, setMeasurementPoints] = useState<Coordinate[]>([]);
  const [locationQuery, setLocationQuery] = useState("");
  const [locationMessage, setLocationMessage] = useState<string | null>(null);

  useEffect(() => {
    onAssetSelectedRef.current = onAssetSelected;
  }, [onAssetSelected]);
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);
  useEffect(() => { measurementModeRef.current = measurementMode; }, [measurementMode]);

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
    active.on("click", (event) => { const point: Coordinate = [event.lngLat.lng, event.lngLat.lat]; onMapClickRef.current?.(point); if (measurementModeRef.current !== "none") setMeasurementPoints(points => [...points, point]); });
    map.current = active;

    return () => {
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      active.remove();
      locationMarker.current?.remove();
      locationMarker.current = null;
      selectionMarker.current?.remove();
      selectionMarker.current = null;
      map.current = null;
    };
  }, [apiBaseUrl, token]);

  useEffect(() => {
    const active = map.current;
    if (!active) return;
    selectionMarker.current?.remove();
    selectionMarker.current = null;
    if (!selectionLocation) return;
    const markerElement = document.createElement("span");
    markerElement.className = "map-location-marker map-selection-marker";
    markerElement.setAttribute(
      "aria-label",
      "Localização selecionada para cadastro",
    );
    selectionMarker.current = new maplibregl.Marker({
      element: markerElement,
      anchor: "center",
    })
      .setLngLat(selectionLocation)
      .addTo(active);
  }, [selectionLocation]);

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
      for (const layerId of ["field-areas", "field-lines"]) {
        if (active.getLayer(layerId)) active.removeLayer(layerId);
      }
      if (active.getSource(fieldSourceId)) active.removeSource(fieldSourceId);
      active.addSource(fieldSourceId, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: fields.map((field) => ({
            type: "Feature",
            properties: { id: field.id, name: field.name, status: field.status },
            geometry: field.geometry_geojson,
          })),
        },
      });
      const before = active.getLayer("property-outline-halo")
        ? "property-outline-halo"
        : undefined;
      active.addLayer(
        {
          id: "field-areas",
          type: "fill",
          source: fieldSourceId,
          filter: ["==", "$type", "Polygon"],
          paint: { "fill-color": "#2563eb", "fill-opacity": 0.18 },
        },
        before,
      );
      active.addLayer(
        {
          id: "field-lines",
          type: "line",
          source: fieldSourceId,
          filter: ["==", "$type", "Polygon"],
          paint: { "line-color": "#1d4ed8", "line-width": 2.5 },
        },
        before,
      );
    };
    if (active.isStyleLoaded()) update();
    active.on("style.load", update);
    return () => {
      active.off("style.load", update);
    };
  }, [fields]);

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

  const findCoordinates = () => {
    const result = parseCoordinates(locationQuery);
    const active = map.current;
    if (!result || !active) {
      setLocationMessage("Informe coordenadas válidas em longitude, latitude (por exemplo, -47.45, -24.49).");
      return;
    }
    locationMarker.current?.remove();
    const markerElement = document.createElement("span");
    markerElement.className = "map-location-marker";
    markerElement.setAttribute("aria-label", `Localização buscada: ${result.label}`);
    locationMarker.current = new maplibregl.Marker({ element: markerElement, anchor: "center" })
      .setLngLat([result.longitude, result.latitude])
      .addTo(active);
    active.easeTo({ center: [result.longitude, result.latitude], zoom: Math.max(active.getZoom(), 15), duration: 500 });
    setLocationMessage(`Localização exibida: ${result.label}. Esta busca não altera o limite cadastrado.`);
  };

  return (
    <div className="map-frame">
      <div className="map-canvas" ref={element} aria-label="Mapa da propriedade" />
      {!basemapStatus.isConfigured && <p className="map-basemap-unavailable">Mapa base não configurado. O limite e os ativos cadastrados continuam disponíveis neste mapa.</p>}
      <button className="map-recenter" type="button" onClick={() => fitPropertyRef.current?.()}>
        Centralizar sítio
      </button>
      <form className="map-location-search" onSubmit={(event) => { event.preventDefault(); findCoordinates(); }}>
        <label htmlFor="map-location-query">Ir para coordenadas</label>
        <div>
          <input id="map-location-query" value={locationQuery} onChange={(event) => setLocationQuery(event.target.value)} placeholder="longitude, latitude" inputMode="decimal" />
          <button type="submit">Buscar</button>
        </div>
        {locationMessage && <p role="status">{locationMessage}</p>}
      </form>
      <div className="map-measure-tools"><button type="button" onClick={() => { setMeasurementMode("distance"); setMeasurementPoints([]); }}>Medir distância</button><button type="button" onClick={() => { setMeasurementMode("area"); setMeasurementPoints([]); }}>Medir área</button><button type="button" onClick={() => { setMeasurementMode("coordinates"); setMeasurementPoints([]); }}>Coordenadas</button>{measurementMode !== "none" && <><button type="button" onClick={() => setMeasurementPoints(points => points.slice(0, -1))}>Desfazer</button><button type="button" onClick={() => { setMeasurementMode("none"); setMeasurementPoints([]); }}>Limpar</button><p>{measurementMode === "distance" ? `${(distanceMetres(measurementPoints) / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} km` : measurementMode === "area" ? `${(areaSquareMetres(measurementPoints) / 10000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} ha` : measurementPoints.at(-1) ? `${measurementPoints.at(-1)![1].toFixed(5)}, ${measurementPoints.at(-1)![0].toFixed(5)}` : "Clique no mapa"}</p></>}</div>
    </div>
  );
}
