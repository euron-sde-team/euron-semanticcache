import { expect, test } from "@playwright/test";
import { ask, KEY, openConsole, RUN, trackErrors } from "../helpers";

const NS = `pw-${RUN}`;
const LONG = "Please write a detailed summary of the quarterly sales report for {} including every key metric";

async function send(page: import("@playwright/test").Page, text: string) {
  await page.getByLabel("Prompt").fill(text);
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

test("connect screen rejects a bad key and accepts the right one", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "Disconnect" }).click();
  await page.getByLabel("API key").fill("sc_bad00000_wrong");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.locator("form [role=alert]")).toContainText(/invalid or revoked/i);
  await page.getByLabel("API key").fill(KEY);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});

test("overview shows savings, hit rate, the breakdown and namespaces", async ({ page, request }) => {
  const errors = trackErrors(page);
  await ask(request, "overview seed question", `ov-${RUN}`);
  await ask(request, "overview seed question", `ov-${RUN}`);
  await openConsole(page);
  await expect(page.getByTestId("stat-saved")).toContainText("$");
  await expect(page.getByTestId("stat-hit-rate")).toContainText("%");
  await expect(page.getByTestId("breakdown")).toContainText("Exact hits");
  await expect(page.getByRole("img", { name: /Requests per minute/ })).toBeVisible();
  await expect(page.getByTestId("namespace-row").first()).toBeVisible();
  await expect(page.getByTestId("sidebar-saved")).toContainText("$");
  expect(errors).toEqual([]);
});

test("playground: miss, exact hit, then a semantic hit on a paraphrase", async ({ page }) => {
  await openConsole(page, "/playground");
  await page.getByLabel("Namespace").fill(NS);
  await page.getByTestId("preset-Reset password").click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=MISS]")).toBeVisible();
  await expect(page.getByTestId("answer")).toContainText("Settings");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=HIT]")).toContainText("exact");
  await page.getByTestId("preset-Paraphrase").click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=HIT]")).toContainText("semantic");
  await expect(page.getByTestId("result")).toContainText(/saved \$/);
  await expect(page.getByTestId("session-summary")).toContainText("2 of 3 from cache");
});

test("playground: a look-alike with a different number is NOT served from cache", async ({ page }) => {
  await openConsole(page, "/playground");
  await page.getByLabel("Namespace").fill(`${NS}-guard`);
  await send(page, LONG.replace("{}", "region 4"));
  await expect(page.getByTestId("result").locator("[data-result=MISS]")).toBeVisible();
  await send(page, LONG.replace("{}", "region 5"));
  await expect(page.getByTestId("result").locator("[data-result=MISS]")).toBeVisible();
  await expect(page.getByTestId("guard-note")).toContainText("numbers differ");
});

test("playground: cache modes", async ({ page }) => {
  await openConsole(page, "/playground");
  await page.getByLabel("Namespace").fill(`${NS}-modes`);
  await page.getByTestId("preset-Capital of France").click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=MISS]")).toBeVisible();
  await page.getByLabel("Cache mode").selectOption("bypass");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=BYPASS]")).toBeVisible();
  await page.getByLabel("Cache mode").selectOption("only-if-cached");
  await page.getByLabel("Prompt").fill("something that was never asked before 98765");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("result").locator("[data-result=ERROR]")).toBeVisible();
  await expect(page.getByTestId("result").getByRole("alert")).toContainText(/not in cache/);
});

test("playground: the demo sequence shows a mix of hits and misses", async ({ page }) => {
  await openConsole(page, "/playground");
  await page.getByLabel("Namespace").fill(`${NS}-demo`);
  await page.getByTestId("run-demo").click();
  await expect(page.getByTestId("log-row")).toHaveCount(7, { timeout: 45_000 });
  const hits = await page.locator("[data-testid=log-row][data-result=HIT]").count();
  const misses = await page.locator("[data-testid=log-row][data-result=MISS]").count();
  expect(hits).toBeGreaterThanOrEqual(3);
  expect(misses).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId("session-summary")).toContainText(/cache .* vs provider/);
});

test("similarity lab explains why a near match would or would not be served", async ({ page, request }) => {
  const ns = `lab-${RUN}`;
  await ask(request, LONG.replace("{}", "region 4"), ns);
  await ask(request, "How do I reset my password?", ns);
  await openConsole(page, "/lab");
  await page.getByLabel("Namespace").fill(ns);
  await page.getByLabel("Prompt").fill("how can I reset my password");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByTestId("neighbors")).toContainText("threshold");
  await expect(page.locator("[data-testid=neighbor][data-hit=true]").first()).toContainText("Would hit");
  await page.getByLabel("Prompt").fill(LONG.replace("{}", "region 5"));
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByTestId("neighbors")).toContainText("Blocked: numbers differ");
});

test("entries: search, open, invalidate", async ({ page, request }) => {
  const ns = `ent-${RUN}`;
  for (const q of ["alpha entry question", "beta entry question", "alpha entry again"]) await ask(request, q, ns);
  await openConsole(page, `/entries?namespace=${ns}`);
  await expect(page.getByTestId("entries-total")).toContainText("3 entries");
  await page.getByLabel("Search prompts").fill("alpha");
  await expect(page.getByTestId("entries-total")).toContainText("2 entries");
  await page.getByTestId("entry-row").first().click();
  const detail = page.getByTestId("entry-detail");
  await expect(detail).toContainText("Cached answer");
  await expect(detail).toContainText("Saved per hit");
  await detail.getByRole("button", { name: "Invalidate" }).click();
  await expect(page.getByText("Entry invalidated")).toBeVisible();
  await expect(page.getByTestId("entries-total")).toContainText("1 entry");
});

test("entries: flush a namespace after confirming", async ({ page, request }) => {
  const ns = `flush-${RUN}`;
  await ask(request, "to be flushed one", ns);
  await ask(request, "to be flushed two", ns);
  await openConsole(page, `/entries?namespace=${ns}`);
  await page.getByRole("button", { name: "Flush namespace" }).click();
  await page.getByRole("button", { name: /Delete \d+ entries/ }).click();
  await expect(page.getByText(/Removed 2 entries/)).toBeVisible();
  await expect(page.getByText("Nothing cached yet")).toBeVisible();
});

test("namespaces: create, tune the threshold, save and delete", async ({ page }) => {
  const name = `ns-${RUN}`;
  await openConsole(page, "/namespaces");
  await page.getByRole("button", { name: "New namespace" }).first().click();
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  const card = page.locator(`[data-testid=namespace-card][data-namespace=${name}]`);
  await expect(card).toBeVisible();
  await expect(card.getByTestId("threshold-value")).toHaveText("0.85");
  const slider = card.getByLabel(`Similarity threshold for ${name}`);
  await slider.focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
  await expect(card.getByTestId("threshold-value")).toHaveText("0.90");
  await card.getByRole("switch", { name: "Safety guards (numbers, IDs, negation)" }).click();
  await card.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(`Saved ${name}`)).toBeVisible();
  await expect(card.getByRole("button", { name: "Save" })).toBeDisabled();
  await card.getByRole("button", { name: `Delete ${name}` }).click();
  await page.getByRole("button", { name: "Delete namespace" }).click();
  await expect(card).toHaveCount(0);
});

test("namespaces: snapshot to S3 (Floci) and restore", async ({ page, request }) => {
  const ns = `snap-${RUN}`;
  await ask(request, "snapshot me please", ns);
  await openConsole(page, "/namespaces");
  const card = page.locator(`[data-testid=namespace-card][data-namespace=${ns}]`);
  await expect(card).toBeVisible({ timeout: 20_000 });
  await card.getByRole("button", { name: "Snapshot to S3" }).click();
  await expect(page.getByText(/written to s3:\/\/semanticcache-local-exports\/exports\//)).toBeVisible();
  await card.getByRole("button", { name: "Flush" }).click();
  await page.getByRole("button", { name: "Flush entries" }).click();
  await card.getByRole("button", { name: "Restore…" }).click();
  await expect(page.getByTestId("snapshots")).toBeVisible();
  await page.getByTestId("snapshots").getByRole("button", { name: "Restore" }).first().click();
  await expect(page.getByText(/Restored 1 entries/)).toBeVisible();
  expect((await ask(request, "snapshot me please", ns, {})).result).toBe("HIT");
});

test("settings: a namespace-bound key is shown once, then revoked", async ({ page }) => {
  await openConsole(page, "/settings");
  const keyName = `ui-key-${RUN}`;
  await page.getByRole("button", { name: "Create API key" }).click();
  await page.getByLabel("Name").fill(keyName);
  await page.getByLabel(/Bind to a namespace/).fill("tenant-ui");
  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByTestId("new-key")).toContainText(/^sc_/);
  await page.getByRole("button", { name: "Done" }).click();
  const row = page.locator("[data-testid=key-row]", { hasText: keyName });
  await expect(row).toContainText("tenant-ui");
  await row.getByRole("button", { name: new RegExp(`Revoke ${keyName}`) }).click();
  await expect(row.getByText("revoked")).toBeVisible();
});

test("theme toggle persists across reloads", async ({ page }) => {
  await openConsole(page);
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await page.getByRole("button", { name: /Switch to (light|dark) theme/ }).click();
  const after = await html.getAttribute("data-theme");
  expect(after).not.toBe(before);
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", after!);
  await page.getByRole("button", { name: /Switch to (light|dark) theme/ }).click();
});

test("mobile layout has navigation and no horizontal page scroll", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } });
  const page = await ctx.newPage();
  for (const path of ["/", "/playground", "/entries", "/namespaces"]) {
    await openConsole(page, path);
    await expect(page.getByRole("navigation", { name: "Main (mobile)" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
  await ctx.close();
});

test("disconnect returns to the connect screen", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeVisible();
});
