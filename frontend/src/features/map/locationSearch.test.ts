import { describe, expect, it } from "vitest";
import { parseCoordinates } from "./locationSearch";
describe("coordinate search", () => { it("accepts longitude latitude", () => expect(parseCoordinates("-48.24, -24.58")?.longitude).toBe(-48.24)); it("does not silently swap an ambiguous valid pair", () => expect(parseCoordinates("-24.58, -48.24")?.longitude).toBe(-24.58)); it("rejects invalid coordinates", () => expect(parseCoordinates("400, 99")).toBeNull()); });
