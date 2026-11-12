import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, SemanticCacheApi } from "@/lib/api";

const api = new SemanticCacheApi({ apiUrl: "http://api.test", apiKey: "sc_k_secret" });
const body = { model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] };

function mockFetch(status: number, data: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...headers } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
afterEach(() => vi.unstubAllGlobals());

describe("SemanticCacheApi", () => {
  it("sends the key and drops empty query params", async () => {
    const fn = mockFetch(200, { items: [], total: 0, offset: 0, limit: 25 });
    await api.entries({ namespace: "acme", q: "", offset: 25, limit: 25 });
    const [url, init] = fn.mock.calls[0]!;
    expect(url).toBe("http://api.test/v1/cache/entries?namespace=acme&offset=25&limit=25");
    expect((init as RequestInit).headers).toMatchObject({ "X-API-Key": "sc_k_secret" });
  });

  it("turns structured errors into ApiError", async () => {
    mockFetch(403, { error: { code: "forbidden", message: "missing scope 'cache:write'", request_id: "r1" } });
    await expect(api.flush("x")).rejects.toMatchObject({ status: 403, code: "forbidden", requestId: "r1" });
  });

  it("reports an unreachable API clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.namespaces().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toContain("http://api.test");
  });

  it("chat() sets control headers and parses a HIT", async () => {
    const fn = mockFetch(200, {
      choices: [{ message: { content: "Paris." } }],
      semantic_cache: { hit: true, type: "semantic", similarity: 0.93, saved_usd: 0.0004, saved_tokens: 120, saved_ms: 800 },
    }, { "x-semanticcache": "HIT" });
    const r = await api.chat(body, { namespace: "acme", cache: "refresh", ttl: 60, tags: ["a", "b"] });
    const headers = (fn.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    expect(headers).toMatchObject({ "X-SC-Namespace": "acme", "X-SC-Cache": "refresh", "X-SC-TTL": "60", "X-SC-Tags": "a,b" });
    expect(r).toMatchObject({ result: "HIT", type: "semantic", similarity: 0.93, savedUsd: 0.0004, savedTokens: 120, savedMs: 800, content: "Paris.", status: 200 });
    expect(r.elapsedMs).toBeGreaterThanOrEqual(0);
  });

  it("chat() surfaces a rejected near-match on a MISS", async () => {
    mockFetch(200, { choices: [{ message: { content: "Berlin." } }], semantic_cache: { hit: false, rejected_reason: "numbers differ", rejected_similarity: 0.91 } }, { "x-semanticcache": "MISS" });
    const r = await api.chat(body);
    expect(r).toMatchObject({ result: "MISS", rejectedReason: "numbers differ", rejectedSimilarity: 0.91, savedUsd: null });
  });

  it("chat() returns an ERROR result instead of throwing for HTTP errors", async () => {
    mockFetch(504, { error: { code: "not_cached", message: "not in cache" } });
    const r = await api.chat(body, { cache: "only-if-cached" });
    expect(r).toMatchObject({ result: "ERROR", status: 504, error: "not in cache" });
  });

  it("encodes entry ids in paths", async () => {
    const fn = mockFetch(200, { deleted: 1 });
    await api.deleteEntry("a/b", "ns");
    expect(fn.mock.calls[0]![0]).toBe("http://api.test/v1/cache/entries/a%2Fb?namespace=ns");
  });
});
