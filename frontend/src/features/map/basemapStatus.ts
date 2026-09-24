export type BasemapStatus = {
  isConfigured: boolean;
  label: string;
};

type BasemapRuntimeConfiguration = {
  provider?: string;
  styleUrl?: string;
  legacyStyleUrl?: string;
  cartoApiKey?: string;
};

const providerNames: Record<string, string> = {
  carto: "CARTO",
  openfreemap: "OpenFreeMap",
  protomaps: "Protomaps",
  self_hosted: "Mapa base hospedado pela Ribeira",
};

function providerLabel(provider: string | undefined): string {
  const normalized = provider?.trim().toLowerCase();
  if (!normalized) return "Estilo de mapa base configurado";
  return providerNames[normalized] ?? `Provedor configurado: ${provider?.trim()}`;
}

export function describeBasemap(
  configuration: BasemapRuntimeConfiguration,
): BasemapStatus {
  if (configuration.styleUrl || configuration.legacyStyleUrl) {
    return {
      isConfigured: true,
      label: `${providerLabel(configuration.provider)} · referência visual`,
    };
  }
  if (configuration.cartoApiKey) {
    return { isConfigured: true, label: "CARTO · referência visual" };
  }
  return {
    isConfigured: false,
    label: "Indisponível · fundo neutro local",
  };
}

export function runtimeBasemapStatus(): BasemapStatus {
  return describeBasemap({
    provider: import.meta.env.VITE_RIBEIRA_BASEMAP_PROVIDER,
    styleUrl: import.meta.env.VITE_RIBEIRA_BASEMAP_STYLE_URL,
    legacyStyleUrl: import.meta.env.VITE_MAP_STYLE_URL,
    cartoApiKey: import.meta.env.VITE_RIBEIRA_CARTO_BASEMAP_API_KEY,
  });
}
