import { expect, test } from "@playwright/test";

const bootstrapFailures = [
  "Configuração necessária: informe VITE_RIBEIRA_PUBLIC_ORIGIN ou VITE_RIBEIRA_API_URL, e VITE_RIBEIRA_TENANT_ID.",
  "Configuração de origem pública necessária.",
  "Configuração OIDC necessária.",
  "Modo de autenticação inválido.",
];

test("production candidate boots an OIDC application shell", async ({ page }) => {
  const scriptResponses: string[] = [];
  page.on("response", response => {
    if (/\/assets\/index-.*\.js(?:\?|$)/.test(response.url())) {
      scriptResponses.push(`${response.status()}:${response.headers()["content-type"] ?? ""}`);
    }
  });

  await page.goto("/", { waitUntil: "networkidle" });
  for (const failure of bootstrapFailures) {
    await expect(page.getByText(failure, { exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  expect(scriptResponses.some(item => item.startsWith("200:") && /javascript/i.test(item))).toBe(true);
});
