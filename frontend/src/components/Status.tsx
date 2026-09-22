import type { DataStatus } from "../types/farm360";
import { customerStatusLabel } from "../presentation";

export function Status({ value }: { value: DataStatus | string }) {
  return <span className={`status status-${value.toLowerCase()}`} title={`Estado técnico: ${value}`}>{customerStatusLabel(value)}</span>;
}
