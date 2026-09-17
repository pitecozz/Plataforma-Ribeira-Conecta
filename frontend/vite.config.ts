import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // MapLibre derives its worker URL from import.meta.url. Pre-bundling changes
  // that URL to .vite/deps without emitting the sibling worker module.
  optimizeDeps: { exclude: ["maplibre-gl"] },
});
