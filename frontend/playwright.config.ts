import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: process.env.RIBEIRA_PLAYWRIGHT_REPORT_DIR ?? "test-results/report", open: "never" }]],
  use: {
    baseURL: process.env.RIBEIRA_PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.RIBEIRA_BROWSER_EXECUTABLE,
      args: ["--no-sandbox"],
    },
  },
  outputDir: process.env.RIBEIRA_PLAYWRIGHT_OUTPUT_DIR ?? "test-results/e2e",
});
