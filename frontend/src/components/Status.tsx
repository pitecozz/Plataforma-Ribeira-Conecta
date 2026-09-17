import type { DataStatus } from "../types/farm360";
export function Status({ value }: { value: DataStatus | string }) { return <span className={`status status-${value.toLowerCase()}`}>{value}</span>; }
