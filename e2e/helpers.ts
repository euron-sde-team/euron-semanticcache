import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const env = readFileSync(resolve(__dirname, "../deploy/compose/.env"), "utf8");
export const KEY = /SC_BOOTSTRAP_API_KEY=(.+)/.exec(env)![1]!.trim();
export const API = "http://localhost:8180";
export const H = { "X-API-Key": KEY };
export const RUN = Math.random().toString(36).slice(2, 8);

/** Opens the console, connecting with the pre-filled local demo key when the connect screen shows. */
export async function openConsole(page: Page, path = "/") {
  await page.goto(path);
  const connect = page.getByRole("button", { name: "Connect", exact: true });
  const nav = page.getByRole("navigation", { name: /^Main/ });
  await expect(connect.or(nav)).toBeVisible();
  if (await connect.isVisible()) {
    await connect.click();
    await expect(nav).toBeVisible();
  }
}

/** Connects the console as a specific key (e.g. a read-only or namespace-bound one). */
export async function openAs(page: Page, key: string, path = "/") {
  await page.goto("/");
  await page.evaluate((k) => localStorage.setItem("semanticcache.connection", JSON.stringify({ apiUrl: "http://localhost:8180", apiKey: k })), key);
  await page.goto(path);
  await expect(page.getByRole("navigation", { name: /^Main/ })).toBeVisible();
}

/** Collects uncaught page errors and console errors so a test can assert there were none. */
export function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) errors.push(`console: ${m.text()}`);
  });
  return errors;
}

/** Asks through the proxy from the test process (setup, not UI). */
export async function ask(request: import("@playwright/test").APIRequestContext, text: string, ns: string, extra: Record<string, unknown> = {}) {
  const r = await request.post(`${API}/v1/chat/completions`, {
    headers: { ...H, "X-SC-Namespace": ns },
    data: { model: "gpt-4o-mini", messages: [{ role: "user", content: text }], ...extra },
  });
  return { status: r.status(), result: r.headers()["x-semanticcache"], body: await r.json() };
}
