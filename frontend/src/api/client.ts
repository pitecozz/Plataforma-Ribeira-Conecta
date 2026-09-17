import type { NdviProduct, PropertyRecord, Provenance, Scene } from "../types/farm360";

export class ApiError extends Error { constructor(public readonly status: number, message: string) { super(message); } }

export class Farm360Api {
  constructor(private readonly baseUrl: string, private readonly token: string) {}

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, { headers: { Authorization: `Bearer ${this.token}` } });
    if (!response.ok) throw new ApiError(response.status, `Request failed (${response.status})`);
    return response.json() as Promise<T>;
  }

  property(tenantId: string, propertyId: string) { return this.get<PropertyRecord>(`/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}`); }
  scenes(tenantId: string, propertyId: string) { return this.get<{ items: Scene[] }>(`/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/scenes`); }
  products(tenantId: string, propertyId: string) { return this.get<{ items: NdviProduct[] }>(`/v1/tenants/${encodeURIComponent(tenantId)}/properties/${encodeURIComponent(propertyId)}/derived-products`); }
  provenance(tenantId: string, productId: string) { return this.get<Provenance>(`/v1/tenants/${encodeURIComponent(tenantId)}/derived-products/${encodeURIComponent(productId)}/provenance`); }
  tileTemplate(tenantId: string, productId: string) { return `${this.baseUrl}/v1/tenants/${encodeURIComponent(tenantId)}/derived-products/${encodeURIComponent(productId)}/tiles/{z}/{x}/{y}`; }
}
