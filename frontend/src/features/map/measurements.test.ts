import { describe, expect, it } from "vitest";
import { areaSquareMetres, distanceMetres } from "./measurements";
describe("map measurements", () => { it("calculates a geographic path", () => expect(distanceMetres([[-48, -24], [-48.01, -24]])).toBeGreaterThan(900)); it("calculates a temporary polygon area", () => expect(areaSquareMetres([[-48, -24], [-48.01, -24], [-48.01, -24.01]])).toBeGreaterThan(100000)); });
