import type { NdviProduct } from "../../types/farm360";

export function canRenderNdvi(product: NdviProduct | null, enabled: boolean): boolean {
  return Boolean(enabled && product?.processing_status === "SUCCEEDED" && product.checksum);
}
