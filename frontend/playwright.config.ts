import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "test-results/report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.RIBEIRA_BROWSER_EXECUTABLE || "/usr/bin/google-chrome",
      args: ["--no-sandbox"],
    },
  },
  outputDir: "test-results/e2e",
});
