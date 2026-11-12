import { expect, test } from "@playwright/test";
import { execSync } from "node:child_process";
import { API, ask, H, openAs, openConsole, RUN, trackErrors } from "../helpers";

test("unknown route renders the 404 page inside the app", async ({ page }) => {
  const res = await page.goto("/definitely-not-a-page");
  expect(res?.status()).toBe(404);
});

test("cached prompts and answers render as text, never as HTML (XSS)", async ({ page, request }) => {
  const ns = `xss-${RUN}`;
  const evil = "<img src=x onerror=window.__xss=1> <script>window.__xss=1</script>";
  await request.post(`${API}/v1/cache/entries`, {
    headers: { ...H, "X-SC-Namespace": ns },
    data: { model: "gpt-4o-mini", messages: [{ role: "user", content: evil }], response: { choices: [{ message: { role: "assistant", content: evil }, finish_reason: "stop" }] } },
  });
  let dialogs = 0;
  page.on("dialog", (d) => { dialogs++; void d.dismiss(); });
  await openConsole(page, `/entries?namespace=${ns}`);
  await expect(page.getByTestId("entry-row")).toContainText("<img src=x onerror");
  await page.getByTestId("entry-row").click();
  await expect(page.getByTestId("entry-detail")).toContainText("<script>window.__xss=1</script>");
  await page.goto("/playground");
  await page.getByLabel("Namespace").fill(ns);
  await page.getByLabel("Prompt").fill(evil);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("answer")).toContainText("<img src=x onerror");
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(dialogs).toBe(0);
});

test("very long prompts do not break the layout", async ({ page, request }) => {
  const ns = `long-${RUN}`;
  const long = "A".repeat(500);
  await ask(request, long, ns);
  await openConsole(page, `/entries?namespace=${ns}`);
  await expect(page.getByTestId("entry-row")).toBeVisible();
  let overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.goto("/playground");
  await page.getByLabel("Namespace").fill(ns);
  await page.getByLabel("Prompt").fill(long);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("log-row")).toBeVisible();
  overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("entries pagination keeps the URL in sync", async ({ page, request }) => {
  const ns = `page-${RUN}`;
  await Promise.all(Array.from({ length: 30 }, (_, i) => ask(request, `pagination question number ${i} about subject ${i * 13}`, ns)));
  await openConsole(page, `/entries?namespace=${ns}`);
  await expect(page.getByTestId("entries-total")).toContainText("30 entries");
  const first = await page.getByTestId("entry-row").first().getAttribute("data-entry-id");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page).toHaveURL(/page=1/);
  await expect(page.getByTestId("entry-row")).toHaveCount(5);
  await page.getByRole("button", { name: "Previous page" }).click();
  await expect(page.getByTestId("entry-row").first()).toHaveAttribute("data-entry-id", first!);
});

test("a read-only key: settings explains, the playground shows the missing scope", async ({ page, request }) => {
  const created = await (await request.post(`${API}/v1/api-keys`, { headers: H, data: { name: `viewer-${RUN}`, scopes: ["stats:read", "cache:read"] } })).json();
  await openAs(page, created.key, "/settings");
  await expect(page.getByText(/cannot manage API keys/)).toBeVisible();
  await page.goto("/playground");
  await page.getByLabel("Namespace").fill(`ro-${RUN}`);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").getByRole("alert")).toContainText(/missing scope/);
  await request.delete(`${API}/v1/api-keys/${created.prefix}`, { headers: H });
});

test("a namespace-bound key sees only its own tenant in the console", async ({ page, request }) => {
  const mine = `tenant-mine-${RUN}`;
  const theirs = `tenant-theirs-${RUN}`;
  await ask(request, "their confidential question", theirs);
  const created = await (await request.post(`${API}/v1/api-keys`, { headers: H, data: { name: `bound-${RUN}`, scopes: ["proxy:use", "cache:read", "cache:write", "stats:read", "namespaces:write"], namespace: mine } })).json();
  await openAs(page, created.key, "/playground");
  await page.getByLabel("Namespace").fill(mine);
  await page.getByLabel("Prompt").fill("my own question");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=MISS]")).toBeVisible();
  await page.getByLabel("Namespace").fill(theirs);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").getByRole("alert")).toContainText(/bound to namespace/);
  await page.goto("/namespaces");
  await expect(page.getByTestId("namespace-card")).toHaveCount(1);
  await expect(page.getByTestId("namespace-card")).toHaveAttribute("data-namespace", mine);
  await expect(page.locator("body")).not.toContainText(theirs);
  await page.getByTestId("namespace-card").getByRole("switch", { name: "Semantic matching" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/namespace-bound keys cannot change namespace settings/)).toBeVisible();
  await request.delete(`${API}/v1/api-keys/${created.prefix}`, { headers: H });
});

test("a key revoked mid-session shows an auth error instead of hanging", async ({ page, request }) => {
  const created = await (await request.post(`${API}/v1/api-keys`, { headers: H, data: { name: `doomed-${RUN}`, scopes: ["stats:read", "cache:read"] } })).json();
  await openAs(page, created.key, "/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await request.delete(`${API}/v1/api-keys/${created.prefix}`, { headers: H });
  await page.getByRole("navigation", { name: "Main", exact: true }).getByRole("link", { name: "Entries" }).click();
  await expect(page.locator("[role=alert]", { hasText: /invalid or revoked/i }).first()).toBeVisible({ timeout: 20_000 });
});

test("API outage: the console reports it, then recovers on its own", async ({ page }) => {
  test.setTimeout(120_000);
  await openConsole(page, "/");
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  execSync("docker stop -t 2 euron-semanticcache-api-1");
  try {
    await expect(page.getByText("Unreachable", { exact: true })).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText(/Cannot reach the API/).first()).toBeVisible({ timeout: 40_000 });
  } finally {
    execSync("docker start euron-semanticcache-api-1");
  }
  await expect(page.getByText("Connected", { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("tiles")).toContainText("Hit rate", { timeout: 30_000 });
});

test("no console errors across every page", async ({ page }) => {
  const errors = trackErrors(page);
  for (const p of ["/", "/playground", "/lab", "/entries", "/namespaces", "/settings"]) {
    await openConsole(page, p);
    await page.waitForTimeout(700);
  }
  expect(errors).toEqual([]);
});

test("keyboard: Enter opens an entry and Escape closes it", async ({ page, request }) => {
  const ns = `kbd-${RUN}`;
  await ask(request, "keyboard question", ns);
  await openConsole(page, `/entries?namespace=${ns}`);
  await page.getByTestId("entry-row").first().focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
