import { describe, expect, it } from "vitest";

import { formatHectares } from "./formatting";

describe("formatHectares", () => {
  it("rounds customer-facing area without changing the persisted value", () => {
    expect(formatHectares("63.86741722620799")).toBe("63,87");
    expect(formatHectares("12.5")).toBe("12,5");
  });

  it("does not turn missing or malformed values into a number", () => {
    expect(formatHectares(null)).toBeNull();
    expect(formatHectares("not-an-area")).toBeNull();
  });
});
