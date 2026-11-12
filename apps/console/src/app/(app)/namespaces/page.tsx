"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Layers, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useApi, useToast } from "@/components/providers";
import { Modal } from "@/components/ui/overlays";
import { Button, EmptyState, ErrorBanner, Field, Input, PageHeader, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { formatNumber, formatPct, formatTtl, formatUsd } from "@/lib/format";
import type { NamespaceConfig, NamespaceSummary } from "@/lib/types";

const TTLS = [3600, 21_600, 86_400, 604_800, 2_592_000];

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center justify-between gap-3 text-[13px]">
      <span>{label}</span>
      <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
        className={cn("relative h-5 w-9 shrink-0 rounded-full transition", checked ? "bg-accent" : "bg-raised ring-1 ring-line")}>
        <span className={cn("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
      </button>
    </label>
  );
}

function Snapshots({ ns, onClose }: { ns: string; onClose: () => void }) {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const files = useQuery({ queryKey: ["exports", ns], queryFn: () => api.exports(ns), retry: false });
  const restore = useMutation({
    mutationFn: (key: string) => api.importExport(key, ns),
    onSuccess: (r) => { toast("success", `Restored ${r.imported} entries (${r.skipped_expired} expired)`); void qc.invalidateQueries(); onClose(); },
    onError: (e) => toast("error", e.message),
  });
  return (
    <Modal open onClose={onClose} title={`Snapshots of ${ns}`} footer={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      {files.error ? <ErrorBanner error={files.error} /> : files.isLoading ? <Skeleton className="h-16" /> : (files.data ?? []).length === 0
        ? <p className="text-[13px] text-muted">No snapshots yet. Use “Snapshot to S3” on the namespace card.</p>
        : <ul className="divide-y divide-line/60" data-testid="snapshots">{files.data!.map((f) => (
            <li key={f.key} className="flex items-center justify-between gap-3 py-2 text-[13px]">
              <span className="min-w-0"><span className="block truncate font-mono text-xs">{f.key.split("/").pop()}</span><span className="text-xs text-subtle">{(f.size / 1024).toFixed(1)} KB</span></span>
              <Button size="sm" onClick={() => restore.mutate(f.key)} loading={restore.isPending}><RotateCcw className="size-3" />Restore</Button>
            </li>))}</ul>}
    </Modal>
  );
}

function NamespaceCard({ ns }: { ns: NamespaceSummary }) {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const [cfg, setCfg] = useState<NamespaceConfig>(ns.config);
  const [snapshots, setSnapshots] = useState(false);
  const [confirm, setConfirm] = useState<null | "flush" | "delete">(null);
  useEffect(() => setCfg(ns.config), [ns.config]);
  const dirty = JSON.stringify(cfg) !== JSON.stringify(ns.config);
  const refresh = () => void qc.invalidateQueries();

  const save = useMutation({ mutationFn: () => api.putNamespace(ns.name, cfg), onSuccess: () => { toast("success", `Saved ${ns.name}`); refresh(); }, onError: (e) => toast("error", e.message) });
  const snap = useMutation({ mutationFn: () => api.exportNamespace(ns.name), onSuccess: (r) => toast("success", `Snapshot of ${r.entries} entries written to s3://${r.bucket}/${r.key}`), onError: (e) => toast("error", e.message) });
  const flush = useMutation({ mutationFn: () => api.flush(ns.name), onSuccess: (r) => { toast("success", `Removed ${r.deleted} entries`); setConfirm(null); refresh(); }, onError: (e) => toast("error", e.message) });
  const del = useMutation({ mutationFn: () => api.deleteNamespace(ns.name), onSuccess: () => { toast("success", `Deleted ${ns.name}`); setConfirm(null); refresh(); }, onError: (e) => toast("error", e.message) });

  return (
    <section className="card p-4" data-testid="namespace-card" data-namespace={ns.name}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2"><Layers className="size-4 text-subtle" aria-hidden /><h2 className="font-semibold">{ns.name}</h2></div>
        <span className="text-xs text-muted">{formatNumber(ns.entries)} entries · {formatPct(ns.hit_rate)} hit · <span className="text-completed">{formatUsd(ns.cost_saved_usd)}</span></span>
      </div>
      <div className="space-y-4">
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[13px]"><label htmlFor={`thr-${ns.name}`}>Similarity threshold</label><b className="tabular-nums" data-testid="threshold-value">{cfg.threshold.toFixed(2)}</b></div>
          <input id={`thr-${ns.name}`} type="range" min={0.5} max={1} step={0.01} value={cfg.threshold} onChange={(e) => setCfg({ ...cfg, threshold: Number(e.target.value) })} className="w-full accent-[rgb(var(--accent))]" aria-label={`Similarity threshold for ${ns.name}`} />
          <p className="mt-1 text-xs text-subtle">Higher is stricter: fewer hits, fewer wrong answers. 1.00 means exact matches only.</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Time to live">
            <select value={TTLS.includes(cfg.ttl_seconds) ? cfg.ttl_seconds : "custom"} onChange={(e) => e.target.value !== "custom" && setCfg({ ...cfg, ttl_seconds: Number(e.target.value) })} aria-label="Time to live"
              className="h-9 w-full rounded-lg border border-line bg-bg px-3 text-[13px]">
              {TTLS.map((t) => <option key={t} value={t}>{formatTtl(t)}</option>)}
              {!TTLS.includes(cfg.ttl_seconds) && <option value="custom">{formatTtl(cfg.ttl_seconds)}</option>}
            </select>
          </Field>
          <Field label="Max entries"><Input type="number" min={10} max={200000} value={cfg.max_entries} onChange={(e) => setCfg({ ...cfg, max_entries: Number(e.target.value) })} aria-label="Max entries" /></Field>
        </div>
        <div className="space-y-2.5 rounded-lg border border-line p-3">
          <Switch label="Caching enabled" checked={cfg.enabled} onChange={(v) => setCfg({ ...cfg, enabled: v })} />
          <Switch label="Semantic matching" checked={cfg.semantic} onChange={(v) => setCfg({ ...cfg, semantic: v })} />
          <Switch label="Safety guards (numbers, IDs, negation)" checked={cfg.guards} onChange={(v) => setCfg({ ...cfg, guards: v })} />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <Button variant="primary" size="sm" onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}><Save className="size-3.5" />Save</Button>
        <Button size="sm" onClick={() => snap.mutate()} loading={snap.isPending}><Archive className="size-3.5" />Snapshot to S3</Button>
        <Button size="sm" variant="ghost" onClick={() => setSnapshots(true)}><RotateCcw className="size-3.5" />Restore…</Button>
        <span className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => setConfirm("flush")} disabled={ns.entries === 0}>Flush</Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirm("delete")} aria-label={`Delete ${ns.name}`}><Trash2 className="size-3.5" /></Button>
        </span>
      </div>
      {snapshots && <Snapshots ns={ns.name} onClose={() => setSnapshots(false)} />}
      <Modal open={confirm !== null} onClose={() => setConfirm(null)} title={confirm === "delete" ? `Delete ${ns.name}?` : `Flush ${ns.name}?`}
        footer={<><Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button><Button variant="danger" loading={flush.isPending || del.isPending} onClick={() => (confirm === "delete" ? del.mutate() : flush.mutate())}>{confirm === "delete" ? "Delete namespace" : "Flush entries"}</Button></>}>
        <p className="text-[13px] text-muted">{confirm === "delete" ? "Removes the namespace, its settings, entries and statistics." : "Removes every cached answer. Settings and statistics are kept."}</p>
      </Modal>
    </section>
  );
}

export default function NamespacesPage() {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["namespaces"], queryFn: () => api.namespaces(), refetchInterval: 5000 });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.putNamespace(name.trim(), { threshold: 0.85, ttl_seconds: 86_400, max_entries: 5000, enabled: true, semantic: true, guards: true }),
    onSuccess: () => { toast("success", `Created ${name.trim()}`); setCreating(false); setName(""); void qc.invalidateQueries(); },
    onError: (e) => toast("error", e.message),
  });
  return (
    <>
      <PageHeader title="Namespaces" description="A namespace is a tenant, an app or an environment. Answers never cross namespaces, and each has its own threshold, lifetime and size."
        actions={<Button variant="primary" onClick={() => setCreating(true)}><Plus className="size-3.5" />New namespace</Button>} />
      {list.error && <ErrorBanner error={list.error} onRetry={() => void list.refetch()} />}
      {list.isLoading && <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-72" /><Skeleton className="h-72" /></div>}
      {list.data?.length === 0 && <div className="card"><EmptyState icon={<Layers className="size-5" />} title="No namespaces yet" hint="Create one, or send a request through the proxy and it is created for you." action={<Button variant="primary" onClick={() => setCreating(true)}><Plus className="size-3.5" />New namespace</Button>} /></div>}
      <div className="grid gap-4 xl:grid-cols-2">{list.data?.map((ns) => <NamespaceCard key={ns.name} ns={ns} />)}</div>
      <Modal open={creating} onClose={() => setCreating(false)} title="New namespace"
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>Create</Button></>}>
        <Field label="Name" hint="Letters, digits, dot, dash and underscore."><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="acme-support" name="namespaceName" autoFocus /></Field>
      </Modal>
    </>
  );
}
