const statusLabels: Record<string, string> = {
  UNKNOWN: "Ainda não disponível",
  DADO_INSUFICIENTE: "Ainda não há dados suficientes para esta análise",
  SOURCE_UNAVAILABLE: "Não foi possível atualizar esta informação agora",
  INCONCLUSIVE: "Evidências ainda inconclusivas",
  MANUAL_CONFIRMED: "Confirmado",
  OFFICIAL_SOURCE: "Fonte oficial",
  READY: "Disponível",
  ACTIVE: "Ativo",
  BETA: "Beta",
  COMING_SOON: "Em breve",
  FOUNDATION: "Em preparação",
  DEFERRED: "Adiado",
};

const sourceLabels: Record<string, string> = {
  USER_PROVIDED_GOOGLE_EARTH_KML:
    "Limite fornecido pelo proprietário (Google Earth)",
  MANUAL_CONFIRMED: "Informação confirmada manualmente",
};

const assetTypeLabels: Record<string, string> = {
  SHED: "Barracão",
  HOUSE_BUILDING: "Casa / edificação",
  HOUSE: "Casa / edificação",
  BUILDING: "Edificação",
  CAMERA: "Câmera",
  CAMERA_IA: "Câmera",
  AI_CAMERA: "Câmera",
  SECURITY_CAMERA: "Câmera",
  RAIN_GAUGE: "Pluviômetro",
};

export function customerStatusLabel(value: string | null | undefined): string {
  if (!value) return "Ainda não disponível";
  return statusLabels[value] ?? value.replaceAll("_", " ");
}

export function customerSourceLabel(value: string | null | undefined): string {
  if (!value) return "Fonte ainda não informada";
  return sourceLabels[value] ?? value.replaceAll("_", " ");
}

export function customerAssetTypeLabel(value: string): string {
  return assetTypeLabels[value] ?? value.replaceAll("_", " ");
}

export function customerPropertyName(value: string): string {
  return value === "TEST_AOI_ONLY" ? "Área de validação" : value;
}

export function customerDateLabel(value: string | null | undefined): string {
  if (!value) return "Ainda não informado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data ainda não disponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(date);
}
