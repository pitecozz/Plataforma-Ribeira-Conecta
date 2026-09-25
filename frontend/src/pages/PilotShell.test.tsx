import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Farm360Api } from "../api/client";
import { PilotShell } from "./PilotShell";

vi.mock("./HomePage", () => ({
  HomePage: ({ onOpenFarm360 }: { onOpenFarm360: (propertyId: string) => void }) => (
    <button type="button" onClick={() => onOpenFarm360("property-1")}>Abrir teste</button>
  ),
}));

vi.mock("./PropertyWorkspace", () => ({
  PropertyWorkspace: ({
    canEvaluateAssets,
    canEvaluateFields,
    canEvaluateTemporalDelta,
  }: {
    canEvaluateAssets: boolean;
    canEvaluateFields: boolean;
    canEvaluateTemporalDelta: boolean;
  }) => <div>{`${canEvaluateAssets}:${canEvaluateFields}:${canEvaluateTemporalDelta}`}</div>,
}));

afterEach(cleanup);

describe("PilotShell permissions", () => {
  it("does not expose evaluation controls from read permissions alone", async () => {
    const api = {
      access: vi.fn().mockResolvedValue({
        permissions: ["asset:read", "property:read", "decision:read", "geospatial:read"],
      }),
    } as unknown as Farm360Api;

    render(<PilotShell api={api} apiBaseUrl="/api" tenantId="tenant" token="token" />);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Abrir teste" }));

    expect(screen.getByText("false:false:false")).toBeInTheDocument();
  });

  it("exposes evaluation controls only with decision:evaluate and subject read access", async () => {
    const api = {
      access: vi.fn().mockResolvedValue({
        permissions: ["asset:read", "property:read", "decision:evaluate", "geospatial:read"],
      }),
    } as unknown as Farm360Api;

    render(<PilotShell api={api} apiBaseUrl="/api" tenantId="tenant" token="token" />);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Abrir teste" }));

    expect(screen.getByText("true:true:true")).toBeInTheDocument();
  });
});
