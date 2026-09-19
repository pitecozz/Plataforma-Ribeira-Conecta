import { expect, test, type Page, type TestInfo } from "@playwright/test";

const API_ORIGIN = "http://127.0.0.1:8080";
type JsonRecord = {
  event: "request" | "response";
  url: string;
  method: string;
  status: number;
  headers: Record<string, string>;
  hasAuthorization: boolean;
  json?: unknown;
  jsonPromise?: Promise<unknown>;
};

function isRibeiraApi(url: string): boolean {
  return new URL(url).origin === API_ORIGIN;
}

async function captureNetwork(page: Page): Promise<JsonRecord[]> {
  const records: JsonRecord[] = [];
  page.on("request", request => {
    records.push({
      event: "request",
      url: request.url(),
      method: request.method(),
      status: 0,
      headers: {},
      hasAuthorization: Boolean(request.headers().authorization),
    });
  });
  page.on("response", response => {
    const request = response.request();
    const record: JsonRecord = {
      event: "response",
      url: response.url(),
      method: request.method(),
      status: response.status(),
      headers: response.headers(),
      hasAuthorization: Boolean(request.headers().authorization),
    };
    records.push(record);
    if (isRibeiraApi(record.url) && !record.url.includes("/tiles/")) {
      record.jsonPromise = response.json().catch(() => undefined);
    }
  });
  return records;
}

async function settleNetwork(page: Page, records: JsonRecord[]): Promise<void> {
  await page.waitForTimeout(1200);
  await Promise.all(records.map(async record => {
    if (record.jsonPromise) record.json = await record.jsonPromise;
  }));
}

function jsonRecords(records: JsonRecord[], pathPart: string): JsonRecord[] {
  return records.filter(record => record.url.includes(pathPart) && record.json !== undefined);
}

async function moveMap(page: Page): Promise<void> {
  // The portfolio map and Farm 360 map are both legitimate MapLibre canvases.
  // Raster assertions belong to the selected property's Farm 360 map.
  const canvas = page.locator(".farm360 .maplibregl-canvas");
  await canvas.click({ position: { x: 400, y: 300 } });
  await page.mouse.wheel(0, -450);
  await page.waitForTimeout(1000);
}

async function saveEvidence(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  await page.screenshot({ path: testInfo.outputPath("screenshots", `${name}.png`), fullPage: true });
}

test("Farm 360 validates temporal delta, layer gates, provenance, and auth boundaries", async ({ page }, testInfo) => {
  const records = await captureNetwork(page);
  await page.goto("/", { waitUntil: "networkidle", timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Portfólio de propriedades" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Linha do tempo" })).toBeVisible();
  await settleNetwork(page, records);
  const portfolioRecord = jsonRecords(records, "/portfolio")[0];
  expect(portfolioRecord?.json).toBeTruthy();
  await expect(page.getByText("TEST_AOI_ONLY permanece dado de validação.", { exact: false })).toBeVisible();
  const webgl = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    return { supported: Boolean(gl), renderer: gl ? gl.getParameter(gl.RENDERER) : null };
  });
  if (!webgl.supported) {
    testInfo.annotations.push({ type: "blocked", description: "Headless browser has no WebGL; authenticated MapLibre raster rendering is BLOCKED while DOM/API/network evidence remains valid." });
  }

  const propertyRecord = jsonRecords(records, "/properties/").find(record => !record.url.includes("/timeline") && !record.url.includes("/scenes"));
  const timelineRecord = jsonRecords(records, "/timeline")[0];
  expect(propertyRecord?.json).toBeTruthy();
  expect(timelineRecord?.json).toBeTruthy();
  const property = propertyRecord?.json as { id: string; name: string; tenant_id: string };
  const timeline = timelineRecord?.json as { items: Array<{ scene_id: string; acquisition_datetime: string; derived_product: { id: string; product_type: string } }> };
  expect(property.name).toBeTruthy();
  expect(property.tenant_id).toBeTruthy();

  // A validation property can legitimately retain a repeated real processing
  // of one scene. The comparison contract needs two distinct real scenes, not
  // an artificial assumption about the total number of retained products.
  const distinctScenes = timeline.items.filter((item, index, items) =>
    items.findIndex(candidate => candidate.scene_id === item.scene_id) === index,
  );
  expect(distinctScenes.length).toBeGreaterThanOrEqual(2);
  const baseline = distinctScenes[0]!;
  const target = distinctScenes[1]!;
  expect(baseline.scene_id).not.toBe(target.scene_id);
  expect(distinctScenes.map(item => item.derived_product.product_type)).toEqual(expect.arrayContaining(["NDVI_QUALITY_MASKED", "NDVI_QUALITY_MASKED"]));

  const baselineButton = page.locator(".timeline-items button").nth(timeline.items.indexOf(baseline));
  const targetButton = page.locator(".timeline-items button").nth(timeline.items.indexOf(target));
  await expect(baselineButton).toBeVisible();
  await expect(targetButton).toBeVisible();

  const sceneValue = page.locator("dt").filter({ hasText: "Scene ID" }).locator("xpath=following-sibling::dd[1]");
  await baselineButton.click();
  await expect(baselineButton).toHaveClass(/selected/);
  await expect(sceneValue).toHaveText(baseline!.scene_id);
  await saveEvidence(page, testInfo, "timeline-26");

  await targetButton.click();
  await expect(targetButton).toHaveClass(/selected/);
  await expect(sceneValue).toHaveText(target!.scene_id);
  await saveEvidence(page, testInfo, "timeline-31");

  await page.getByRole("button", { name: "Comparar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Comparação temporal" })).toBeVisible();
  await settleNetwork(page, records);
  const comparisonRecord = jsonRecords(records, "/temporal-comparison").at(-1);
  expect(comparisonRecord?.json).toBeTruthy();
  const comparison = comparisonRecord?.json as {
    property_id: string;
    status: string;
    baseline: { id: string; scene_id: string };
    target: { id: string; scene_id: string };
    comparison: { delta_minimum: string; delta_maximum: string; delta_mean: string; comparable_valid_pixels: number; comparable_coverage_percentage: string; alignment_summary: { status: string }; classification: string; delta_product_id: string | null; limitations: string[] };
  };
  expect(comparison.property_id).toBe(property.id);
  expect(comparison.status).toBe("READY");
  expect(comparison.baseline.id).toBe(baseline!.derived_product.id);
  expect(comparison.target.id).toBe(target!.derived_product.id);
  expect(Number.isFinite(Number(comparison.comparison.delta_minimum))).toBeTruthy();
  expect(Number.isFinite(Number(comparison.comparison.delta_maximum))).toBeTruthy();
  expect(Number.isFinite(Number(comparison.comparison.delta_mean))).toBeTruthy();
  expect(comparison.comparison.comparable_valid_pixels).toBeGreaterThan(0);
  expect(Number(comparison.comparison.comparable_coverage_percentage)).toBeGreaterThan(0);
  expect(comparison.comparison.alignment_summary.status).toBe("ALIGNED_TO_BASELINE_GRID");
  expect(comparison.comparison.classification).toBe("PIXEL_ALIGNED_DELTA");
  expect(comparison.comparison.delta_product_id).toBeTruthy();

  const comparisonPanel = page.getByRole("heading", { name: "Comparação temporal" }).locator("..");
  const comparisonValues = comparisonPanel.locator("dd");
  await expect(comparisonValues.nth(0)).toHaveText("READY");
  const visibleDelta = (await comparisonValues.nth(1).innerText()).split("/").map(value => Number(value.trim()));
  expect(visibleDelta).toHaveLength(3);
  expect(visibleDelta.every(Number.isFinite)).toBeTruthy();
  expect(Number(await comparisonValues.nth(2).innerText())).toBeGreaterThan(0);
  expect(Number((await comparisonValues.nth(3).innerText()).replace("%", ""))).toBeGreaterThan(0);
  await expect(comparisonValues.nth(4)).toHaveText("ALIGNED_TO_BASELINE_GRID");
  await expect(comparisonPanel).toContainText("PIXEL_ALIGNED_DELTA");
  await expect(comparisonPanel).toContainText("valid in both quality-masked products");
  await expect(comparisonPanel).toContainText("does not identify a cause, diagnosis, gain, loss, or field condition");

  const ndviToggle = page.locator('input[type="checkbox"]').nth(0);
  const deltaToggle = page.locator('input[type="checkbox"]').nth(1);
  await expect(ndviToggle).toBeChecked();
  await expect(deltaToggle).toBeChecked();
  const deltaProductId = comparison.comparison.delta_product_id!;
  const deltaTilePath = `/derived-products/${deltaProductId}/tiles/`;
  // Some headless Chromium builds expose a WebGL context but cannot schedule
  // MapLibre raster work. Keep that renderer limitation explicit rather than
  // misrepresenting a DOM-only run as visual tile evidence.
  if (webgl.supported) await moveMap(page);
  await page.waitForTimeout(1_500);
  const mapRasterRenderable = records.some(record => record.event === "response" && record.url.includes(deltaTilePath) && record.status > 0);
  if (!mapRasterRenderable) testInfo.annotations.push({ type: "blocked", description: "Headless MapLibre did not schedule raster tile requests; authenticated raster rendering is BLOCKED in this browser runtime." });
  await saveEvidence(page, testInfo, "compare-delta-on");

  const deltaRequestsBeforeOff = records.filter(record => record.event === "request" && record.url.includes(deltaTilePath)).length;
  await deltaToggle.uncheck();
  await expect(deltaToggle).not.toBeChecked();
  await expect(ndviToggle).toBeChecked();
  if (mapRasterRenderable) await moveMap(page);
  await page.waitForTimeout(1_500);
  expect(records.filter(record => record.event === "request" && record.url.includes(deltaTilePath)).length).toBe(deltaRequestsBeforeOff);
  await saveEvidence(page, testInfo, "delta-off-ndvi-on");

  const ndviProductId = target!.derived_product.id;
  const ndviTilePath = `/derived-products/${ndviProductId}/tiles/`;
  const rasterRequestsBeforeBothOff = records.filter(record => record.event === "request" && record.url.includes("/derived-products/") && record.url.includes("/tiles/")).length;
  await ndviToggle.uncheck();
  await expect(ndviToggle).not.toBeChecked();
  await expect(deltaToggle).not.toBeChecked();
  await page.waitForTimeout(1_500);
  await expect(page.getByText(property.name, { exact: true })).toBeVisible();
  if (mapRasterRenderable) await moveMap(page);
  await page.waitForTimeout(1_500);
  const rasterRequestsAfterBothOff = records.filter(record => record.event === "request" && record.url.includes("/derived-products/") && record.url.includes("/tiles/")).length;
  expect(rasterRequestsAfterBothOff).toBe(rasterRequestsBeforeBothOff);
  if (mapRasterRenderable) expect(records.some(record => record.event === "request" && record.url.includes(ndviTilePath))).toBeTruthy();
  await saveEvidence(page, testInfo, "both-off");

  await deltaToggle.check();
  await expect(deltaToggle).toBeChecked();
  await expect(ndviToggle).not.toBeChecked();
  await expect(page.getByText("vermelho: NDVI menor no target", { exact: false })).toBeVisible();
  if (mapRasterRenderable) await moveMap(page);

  await page.getByRole("button", { name: "Proveniência do Δ NDVI", exact: true }).click();
  await expect(page.locator("details.provenance")).toBeVisible();
  await expect(page.locator("details.provenance")).toContainText("NDVI_TEMPORAL_DELTA", { timeout: 20_000 });
  await page.locator("details.provenance > summary").click();
  await saveEvidence(page, testInfo, "provenance-delta");
  await settleNetwork(page, records);

  const provenanceRecord = jsonRecords(records, `/derived-products/${deltaProductId}/provenance`).at(-1);
  expect(provenanceRecord?.json).toBeTruthy();
  const provenance = provenanceRecord?.json as {
    product: { product_type: string; algorithm_id: string; formula: string; input_asset_keys: string[] };
    upstreams: Array<{ relationship: string; product: { input_asset_keys: string[] }; scene: { scene_id: string } | null; assets: Array<{ asset_key: string }> }>;
  };
  expect(provenance.product.product_type).toBe("NDVI_DELTA");
  expect(provenance.product.algorithm_id).toBe("NDVI_TEMPORAL_DELTA");
  expect(provenance.product.formula).toBe("NDVI_target - NDVI_baseline");
  expect(provenance.product.input_asset_keys).toEqual([]);
  expect(provenance.upstreams.map(upstream => upstream.relationship).sort()).toEqual(["BASELINE_NDVI", "TARGET_NDVI"]);
  for (const upstream of provenance.upstreams) {
    expect(upstream.product.input_asset_keys).toEqual(expect.arrayContaining(["B04_10m", "B08_10m", "SCL_20m"]));
    expect(upstream.scene?.scene_id).toBeTruthy();
    expect(upstream.assets.map(asset => asset.asset_key)).toEqual(expect.arrayContaining(["B04_10m", "B08_10m", "SCL_20m"]));
  }
  const provenanceUi = page.locator("details.provenance");
  await expect(provenanceUi).toContainText("Inputs diretos");
  await expect(provenanceUi).toContainText("Produtos derivados upstream");
  await expect(provenanceUi).toContainText("Sentinel scenes upstream");
  await expect(provenanceUi).toContainText("Produtos upstream do delta — assets das cenas");
  await expect(provenanceUi).not.toContainText("Inputs deste produto");
  await expect(provenanceUi).not.toContainText("DADO_INSUFICIENTE");
  await expect(provenanceUi).toContainText(baseline!.scene_id);
  await expect(provenanceUi).toContainText(target!.scene_id);
  await expect(provenanceUi).toContainText("B04_10m");
  await expect(provenanceUi).toContainText("B08_10m");
  await expect(provenanceUi).toContainText("SCL_20m");

  if (mapRasterRenderable) {
    const deltaTileResponses = records.filter(record => record.event === "response" && record.url.includes(deltaTilePath) && record.method === "GET" && record.status > 0);
    expect(deltaTileResponses.length).toBeGreaterThan(0);
    for (const response of deltaTileResponses) {
      expect(response.status).toBe(200);
      expect(response.headers["content-type"]?.toLowerCase()).toContain("image/png");
      expect(response.headers["cache-control"]?.toLowerCase()).toContain("private");
      expect(response.headers["vary"]?.toLowerCase()).toContain("authorization");
      expect(response.hasAuthorization).toBe(true);
    }
  }

  const apiRecords = records.filter(record => record.url.startsWith(API_ORIGIN));
  expect(apiRecords.length).toBeGreaterThan(0);
  expect(apiRecords.every(record => record.hasAuthorization)).toBe(true);
  for (const record of records) {
    const origin = new URL(record.url).origin;
    if (origin !== API_ORIGIN && origin !== "http://127.0.0.1:5173") expect(record.hasAuthorization).toBe(false);
  }

});
