// Mirrors the SemanticCache API schema (see docs/api/openapi.yaml).

export interface NamespaceConfig {
  threshold: number;
  ttl_seconds: number;
  max_entries: number;
  enabled: boolean;
  semantic: boolean;
  guards: boolean;
}

export interface NamespaceSummary {
  name: string;
  config: NamespaceConfig;
  entries: number;
  requests: number;
  hits: number;
  misses: number;
  hit_rate: number;
  cost_saved_usd: number;
  tokens_saved: number;
}

export interface Totals {
  requests: number;
  hits: number;
  hits_exact: number;
  hits_semantic: number;
  coalesced: number;
  misses: number;
  bypass: number;
  hit_rate: number;
  tokens_saved: number;
  cost_saved_usd: number;
  cost_spent_usd: number;
  savings_pct: number;
  latency_saved_ms: number;
  avg_latency_saved_ms: number;
  entries: number;
  rejected_guard: number;
  evictions: number;
}

export interface SeriesPoint {
  minute: number;
  hits: number;
  misses: number;
  cost_saved_usd: number;
  tokens_saved: number;
}

export interface Overview {
  totals: Totals;
  namespaces: NamespaceSummary[];
  series: SeriesPoint[];
}

export interface CacheEntry {
  id: string;
  namespace: string;
  model: string;
  prompt: string;
  scope: string;
  response: { choices?: { message?: { content?: string | null } }[] };
  usage: { prompt_tokens: number; completion_tokens: number };
  cost_micro_usd: number;
  latency_ms: number;
  created_at: number;
  expires_at: number | null;
  hits: number;
  last_hit_at: number | null;
  tags: string[];
}

export interface EntryPage {
  items: CacheEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface Neighbor {
  id: string;
  prompt: string;
  similarity: number;
  in_scope: boolean;
  guard: string | null;
  would_hit: boolean;
}

export interface Explain {
  threshold: number;
  guards: boolean;
  neighbors: Neighbor[];
}

export interface ChatBody {
  model: string;
  messages: { role: string; content: string }[];
}

export type CacheMode = "" | "bypass" | "refresh" | "no-store" | "only-if-cached";

export interface ChatResult {
  status: number;
  elapsedMs: number;
  result: "HIT" | "MISS" | "BYPASS" | "COALESCED" | "ERROR";
  type: string | null;
  similarity: number | null;
  savedUsd: number | null;
  savedTokens: number | null;
  savedMs: number | null;
  rejectedReason: string | null;
  rejectedSimilarity: number | null;
  content: string;
  error: string | null;
}

export interface ApiKeyRecord {
  prefix: string;
  name: string;
  scopes: string[];
  namespace: string | null;
  created_at: number;
  last_used_at: number | null;
  revoked: boolean;
}

export interface ApiKeyCreated extends ApiKeyRecord {
  key: string;
}

export interface ExportResult {
  bucket: string;
  key: string;
  entries: number;
}

export interface ExportFile {
  key: string;
  size: number;
  modified: string;
}
