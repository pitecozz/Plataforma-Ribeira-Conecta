export function formatHectares(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value.trim() === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(numeric);
}
