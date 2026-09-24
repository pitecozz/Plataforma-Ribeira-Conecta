import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LayerManager } from "./LayerManager";
describe("LayerManager", () => { it("does not make unavailable analytical layers look active", () => { render(<LayerManager ndviAvailable={false} ndviEnabled={false} onNdviEnabled={vi.fn()} deltaAvailable={false} deltaEnabled={false} onDeltaEnabled={vi.fn()} />); expect(screen.getAllByRole("checkbox")).toHaveLength(2); expect(screen.getAllByRole("checkbox")[0]).toBeDisabled(); expect(screen.getByText(/sem produto processado/)).toBeInTheDocument(); }); });
