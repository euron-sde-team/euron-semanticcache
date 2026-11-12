// Regenerates docs/assets/screenshots/*.png from a running, seeded stack (`make up && make demo`).
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";
import { API, H, openConsole } from "../helpers";

const OUT = resolve(__dirname, "../../docs/assets/screenshots");
const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });
const LONG = "Please write a detailed summary of the quarterly sales report for {} including every key metric";

test("capture every screen", async ({ page, request }) => {
  // A clean playground namespace, so the sequence starts with real misses.
  await request.delete(`${API}/v1/cache/entries`, { headers: { ...H, "X-SC-Namespace": "playground" } });

  await openConsole(page);
  await page.evaluate(() => localStorage.setItem("semanticcache.theme", "dark"));
  await page.reload();
  await expect(page.getByTestId("stat-saved")).toContainText("$");
  await page.waitForTimeout(2500);
  await shot(page, "01-overview");

  // Playground: the demo sequence, then a look-alike that the guard rejects.
  await openConsole(page, "/playground");
  await page.getByLabel("Namespace").fill("playground");
  await page.getByTestId("run-demo").click();
  await expect(page.getByTestId("log-row")).toHaveCount(7, { timeout: 60_000 });
  await page.waitForTimeout(500);
  await shot(page, "02-playground");

  await page.getByLabel("Prompt").fill(LONG.replace("{}", "region 4"));
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("log-row")).toHaveCount(8);
  await page.getByLabel("Prompt").fill(LONG.replace("{}", "region 5"));
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("guard-note")).toContainText("numbers differ");
  await page.waitForTimeout(400);
  await shot(page, "03-guard");

  // Similarity lab on the same namespace.
  await openConsole(page, "/lab");
  await page.getByLabel("Namespace").fill("playground");
  await page.getByLabel("Prompt").fill(LONG.replace("{}", "region 6"));
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByTestId("neighbors")).toContainText("Blocked: numbers differ");
  await page.waitForTimeout(400);
  await shot(page, "04-lab");

  await openConsole(page, "/entries?namespace=acme-support");
  await expect(page.getByTestId("entry-row").first()).toBeVisible();
  await page.waitForTimeout(300);
  await shot(page, "05-entries");
  await page.getByTestId("entry-row").first().click();
  await expect(page.getByTestId("entry-detail")).toBeVisible();
  await page.waitForTimeout(400);
  await shot(page, "06-entry-detail");

  await openConsole(page, "/namespaces");
  await expect(page.getByTestId("namespace-card").first()).toBeVisible();
  await page.waitForTimeout(300);
  await shot(page, "07-namespaces");

  await openConsole(page, "/settings");
  await expect(page.getByTestId("key-row").first()).toBeVisible();
  await shot(page, "08-settings");

  await openConsole(page, "/");
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  await page.waitForTimeout(600);
  await shot(page, "09-overview-light");
  await page.getByRole("button", { name: /Switch to dark theme/ }).click();
});
