import { describe, expect, it } from "vitest";

import { describeBasemap } from "./basemapStatus";

describe("describeBasemap", () => {
  it("does not claim an active provider when no runtime source is configured", () => {
    expect(describeBasemap({})).toEqual({
      isConfigured: false,
      label: "Indisponível · fundo neutro local",
    });
  });

  it("labels the configured provider without promoting it to analytical evidence", () => {
    expect(describeBasemap({ provider: "openfreemap", styleUrl: "https://tiles.openfreemap.org/styles/liberty" })).toEqual({
      isConfigured: true,
      label: "OpenFreeMap · referência visual",
    });
  });
});
