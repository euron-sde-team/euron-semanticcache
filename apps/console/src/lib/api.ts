import type { Connection } from "./connection";
import type {
  ApiKeyCreated, ApiKeyRecord, CacheEntry, CacheMode, ChatBody, ChatResult, EntryPage, ExportFile, ExportResult,
  Explain, NamespaceConfig, NamespaceSummary, Overview,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface ChatOptions {
  namespace?: string;
  cache?: CacheMode;
  ttl?: number;
  tags?: string[];
}

export class SemanticCacheApi {
  constructor(readonly conn: Connection) {}

  private async raw(method: string, path: string, opts: { query?: Query; body?: unknown; headers?: Record<string, string> } = {}): Promise<Response> {
    try {
      return await fetch(`${this.conn.apiUrl}${path}${qs(opts.query)}`, {
        method,
        headers: {
          "X-API-Key": this.conn.apiKey,
          ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
          ...opts.headers,
        },
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      });
    } catch {
      throw new ApiError(0, "network", `Cannot reach the API at ${this.conn.apiUrl}`);
    }
  }

  private async fail(res: Response): Promise<never> {
    let code = "error";
    let message = res.statusText;
    let requestId: string | undefined;
    try {
      const data = (await res.json()) as { error?: { code: string; message: string; request_id?: string } };
      if (data.error) ({ code, message, request_id: requestId } = data.error);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message, requestId);
  }

  private async request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
    const res = await this.raw(method, path, opts);
    if (!res.ok) return this.fail(res);
    return (await res.json()) as T;
  }

  overview = (minutes = 30) => this.request<Overview>("GET", "/v1/stats/overview", { query: { minutes } });
  namespaces = () => this.request<NamespaceSummary[]>("GET", "/v1/namespaces");
  putNamespace = (name: string, config: NamespaceConfig) => this.request<NamespaceSummary>("PUT", `/v1/namespaces/${name}`, { body: config });
  deleteNamespace = (name: string) => this.request<{ ok: boolean }>("DELETE", `/v1/namespaces/${name}`);

  entries = (q: { namespace?: string; q?: string; offset?: number; limit?: number }) => this.request<EntryPage>("GET", "/v1/cache/entries", { query: q });
  deleteEntry = (id: string, namespace?: string) => this.request<{ deleted: number }>("DELETE", `/v1/cache/entries/${encodeURIComponent(id)}`, { query: { namespace } });
  flush = (namespace?: string) => this.request<{ deleted: number }>("DELETE", "/v1/cache/entries", { query: { namespace } });
  explain = (body: ChatBody, namespace?: string) => this.request<Explain>("POST", "/v1/cache/explain", { body: { ...body, k: 10 }, query: { namespace } });

  exportNamespace = (namespace: string) => this.request<ExportResult>("POST", "/v1/cache/export", { body: { namespace } });
  exports = (namespace: string) => this.request<ExportFile[]>("GET", "/v1/cache/exports", { query: { namespace } });
  importExport = (key: string, namespace?: string) => this.request<{ imported: number; skipped_expired: number; namespace: string }>("POST", "/v1/cache/import", { body: { key, namespace } });

  apiKeys = () => this.request<ApiKeyRecord[]>("GET", "/v1/api-keys");
  scopes = () => this.request<string[]>("GET", "/v1/api-keys/scopes");
  createApiKey = (name: string, scopes: string[], namespace?: string) => this.request<ApiKeyCreated>("POST", "/v1/api-keys", { body: { name, scopes, namespace: namespace || null } });
  revokeApiKey = (prefix: string) => this.request<{ ok: boolean }>("DELETE", `/v1/api-keys/${prefix}`);

  /** Sends a chat completion through the cache and measures what the caller experienced. */
  async chat(body: ChatBody, opts: ChatOptions = {}): Promise<ChatResult> {
    const headers: Record<string, string> = {};
    if (opts.namespace) headers["X-SC-Namespace"] = opts.namespace;
    if (opts.cache) headers["X-SC-Cache"] = opts.cache;
    if (opts.ttl) headers["X-SC-TTL"] = String(opts.ttl);
    if (opts.tags?.length) headers["X-SC-Tags"] = opts.tags.join(",");
    const start = performance.now();
    const res = await this.raw("POST", "/v1/chat/completions", { body, headers });
    const elapsedMs = Math.round(performance.now() - start);
    const base: ChatResult = {
      status: res.status, elapsedMs, result: "ERROR", type: null, similarity: null, savedUsd: null, savedTokens: null,
      savedMs: null, rejectedReason: null, rejectedSimilarity: null, content: "", error: null,
    };
    const data = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    if (!res.ok) {
      const err = (data as { error?: { message?: string } } | null)?.error;
      return { ...base, error: err?.message ?? res.statusText };
    }
    const sc = ((data?.semantic_cache as Record<string, unknown> | undefined) ?? {}) as Record<string, number | string | boolean | null>;
    const header = (res.headers.get("x-semanticcache") ?? "MISS") as ChatResult["result"];
    const choices = (data?.choices as { message?: { content?: string | null } }[] | undefined) ?? [];
    return {
      ...base,
      result: header,
      type: (sc.type as string | null) ?? null,
      similarity: typeof sc.similarity === "number" ? sc.similarity : null,
      savedUsd: typeof sc.saved_usd === "number" ? sc.saved_usd : null,
      savedTokens: typeof sc.saved_tokens === "number" ? sc.saved_tokens : null,
      savedMs: typeof sc.saved_ms === "number" ? sc.saved_ms : null,
      rejectedReason: (sc.rejected_reason as string | undefined) ?? null,
      rejectedSimilarity: typeof sc.rejected_similarity === "number" ? sc.rejected_similarity : null,
      content: choices[0]?.message?.content ?? "",
    };
  }

  /** Cheap authenticated call used to validate credentials on the connect screen. */
  async ping(): Promise<void> {
    await this.namespaces();
  }
}

export type { CacheEntry };
