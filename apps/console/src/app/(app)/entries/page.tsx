"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Database, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useApi, useToast } from "@/components/providers";
import { Drawer, Modal } from "@/components/ui/overlays";
import { Button, EmptyState, ErrorBanner, Input, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { useDebounced } from "@/hooks/use-debounced";
import { useUrlState } from "@/hooks/use-url-state";
import { formatDuration, formatTime, formatUsd, prettyJson, relativeTime } from "@/lib/format";
import type { CacheEntry } from "@/lib/types";
import { Suspense } from "react";

const PAGE = 25;
const answer = (e: CacheEntry) => e.response.choices?.[0]?.message?.content ?? "";

function EntryDrawer({ entry, onClose, namespace }: { entry: CacheEntry | null; onClose: () => void; namespace: string }) {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deleteEntry(entry!.id, namespace),
    onSuccess: () => { toast("success", "Entry invalidated"); onClose(); void qc.invalidateQueries(); },
    onError: (e) => toast("error", e.message),
  });
  return (
    <Drawer open={!!entry} onClose={onClose} title={entry ? <div className="min-w-0"><div className="truncate font-semibold">{entry.prompt}</div><div className="truncate font-mono text-[11px] text-subtle">{entry.id}</div></div> : "Entry"}>
      {entry && (
        <div data-testid="entry-detail">
          <div className="border-b border-line px-5 py-3"><Button size="sm" variant="danger" onClick={() => del.mutate()} loading={del.isPending}><Trash2 className="size-3.5" />Invalidate</Button></div>
          <section className="border-b border-line px-5 py-4">
            <h3 className="label mb-2.5">Cached answer</h3>
            <p className="whitespace-pre-wrap rounded-lg border border-line bg-bg p-3 text-[13px] leading-relaxed [overflow-wrap:anywhere]">{answer(entry)}</p>
          </section>
          <section className="border-b border-line px-5 py-4">
            <h3 className="label mb-2.5">Details</h3>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
              {[
                ["Model", entry.model], ["Hits", String(entry.hits)],
                ["Tokens (in / out)", `${entry.usage.prompt_tokens} / ${entry.usage.completion_tokens}`], ["Saved per hit", formatUsd(entry.cost_micro_usd / 1e6)],
                ["Provider latency", formatDuration(entry.latency_ms)], ["Total saved", formatUsd((entry.cost_micro_usd / 1e6) * entry.hits)],
                ["Created", relativeTime(entry.created_at)], ["Expires", entry.expires_at ? relativeTime(entry.expires_at) : "never"],
                ["Last hit", entry.last_hit_at ? relativeTime(entry.last_hit_at) : "never"], ["Scope", entry.scope],
              ].map(([k, v]) => <div key={k}><dt className="text-subtle">{k}</dt><dd className="mt-0.5 truncate font-medium" title={v}>{v}</dd></div>)}
            </dl>
            {entry.tags.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{entry.tags.map((t) => <span key={t} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px] text-muted">{t}</span>)}</div>}
          </section>
          <section className="px-5 py-4"><h3 className="label mb-2.5">Raw response</h3><pre className="max-h-64 overflow-auto rounded-lg border border-line bg-bg p-3 font-mono text-xs">{prettyJson(entry.response)}</pre></section>
        </div>
      )}
    </Drawer>
  );
}

function Entries() {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const url = useUrlState();
  const namespace = url.get("namespace") || "";
  const page = Math.max(0, Number(url.get("page") || 0));
  const [search, setSearch] = useState(url.get("q"));
  const q = useDebounced(search, 300);
  const [open, setOpen] = useState<CacheEntry | null>(null);
  const [confirm, setConfirm] = useState(false);

  // Push the debounced search into the URL once per change (url.set is intentionally not a dependency).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (q !== url.get("q")) url.set({ q: q || null, page: null }); }, [q]);

  const namespaces = useQuery({ queryKey: ["namespaces"], queryFn: () => api.namespaces(), refetchInterval: 5000 });
  const active = namespace || namespaces.data?.[0]?.name || "";
  const list = useQuery({
    queryKey: ["entries", { active, q, page }],
    queryFn: () => api.entries({ namespace: active, q: q || undefined, offset: page * PAGE, limit: PAGE }),
    enabled: !!active, refetchInterval: 4000, placeholderData: (p) => p,
  });
  const flush = useMutation({
    mutationFn: () => api.flush(active),
    onSuccess: (r) => { toast("success", `Removed ${r.deleted} entr${r.deleted === 1 ? "y" : "ies"}`); setConfirm(false); void qc.invalidateQueries(); },
    onError: (e) => toast("error", e.message),
  });

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <>
      <PageHeader title="Entries" description="Everything the cache holds for a namespace, most recently used first."
        actions={active ? <Button variant="danger" onClick={() => setConfirm(true)} disabled={total === 0}><Trash2 className="size-3.5" />Flush namespace</Button> : undefined} />
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-3 py-3">
          <Select aria-label="Namespace" value={active} onChange={(e) => url.set({ namespace: e.target.value, page: null })} className="w-48">
            {(namespaces.data ?? []).map((n) => <option key={n.name} value={n.name}>{n.name} ({n.entries})</option>)}
          </Select>
          <div className="relative ml-auto">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-subtle" />
            <Input aria-label="Search prompts" placeholder="Search prompts" value={search} onChange={(e) => setSearch(e.target.value)} className="w-60 pl-8" />
          </div>
        </div>
        {namespaces.error ? <div className="p-4"><ErrorBanner error={namespaces.error} onRetry={() => void namespaces.refetch()} /></div>
          : list.error ? <div className="p-4"><ErrorBanner error={list.error} onRetry={() => void list.refetch()} /></div>
          : !active ? <EmptyState icon={<Database className="size-5" />} title="No namespaces yet" hint="Send a request through the proxy and its namespace appears here." />
          : list.isLoading ? <div className="space-y-2 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>
          : items.length === 0 ? <EmptyState icon={<Database className="size-5" />} title={q ? "No entries match" : "Nothing cached yet"} hint={q ? "Try a different search." : "Entries appear as soon as a request is answered by the provider."} />
          : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-left text-[13px]">
                <thead><tr className="border-b border-line">{["Prompt", "Model", "Hits", "Tokens", "Saved / hit", "Created", "Expires"].map((h) => <th key={h} className="label px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
                <tbody>
                  {items.map((e) => (
                    <tr key={e.id} tabIndex={0} data-testid="entry-row" data-entry-id={e.id} onClick={() => setOpen(e)} onKeyDown={(ev) => ev.key === "Enter" && setOpen(e)}
                      className="cursor-pointer border-b border-line/60 transition last:border-0 hover:bg-raised/60 focus-visible:bg-raised/60">
                      <td className="max-w-[360px] truncate px-4 py-2.5 font-medium" title={e.prompt}>{e.prompt}</td>
                      <td className="px-4 py-2.5 text-muted">{e.model}</td>
                      <td className="px-4 py-2.5 tabular-nums">{e.hits}</td>
                      <td className="px-4 py-2.5 tabular-nums text-muted">{e.usage.prompt_tokens + e.usage.completion_tokens}</td>
                      <td className="px-4 py-2.5 tabular-nums text-completed">{formatUsd(e.cost_micro_usd / 1e6)}</td>
                      <td className="px-4 py-2.5 text-muted" title={formatTime(e.created_at)}>{relativeTime(e.created_at)}</td>
                      <td className="px-4 py-2.5 text-muted">{e.expires_at ? relativeTime(e.expires_at) : "never"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-muted">
          <span data-testid="entries-total">{total.toLocaleString("en-US")} entr{total === 1 ? "y" : "ies"}</span>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => url.set({ page: String(page - 1) })} aria-label="Previous page"><ChevronLeft className="size-3.5" /></Button>
            <span className="px-1 tabular-nums">{page + 1} / {pages}</span>
            <Button size="sm" variant="ghost" disabled={page + 1 >= pages} onClick={() => url.set({ page: String(page + 1) })} aria-label="Next page"><ChevronRight className="size-3.5" /></Button>
          </div>
        </div>
      </div>
      <EntryDrawer entry={open} onClose={() => setOpen(null)} namespace={active} />
      <Modal open={confirm} onClose={() => setConfirm(false)} title={`Flush ${active}?`}
        footer={<><Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="danger" loading={flush.isPending} onClick={() => flush.mutate()}>Delete {total} entries</Button></>}>
        <p className="text-[13px] text-muted">Every cached answer in this namespace is removed. Statistics are kept. The next requests go to the provider.</p>
      </Modal>
    </>
  );
}

export default function Page() {
  return <Suspense><Entries /></Suspense>;
}
