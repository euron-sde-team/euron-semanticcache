"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eraser, Play, Send, Zap } from "lucide-react";
import { useState } from "react";
import { useApi, useToast } from "@/components/providers";
import { Button, Field, Input, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { ResultBadge } from "@/components/ui/result-badge";
import { cn } from "@/lib/cn";
import { formatDuration, formatUsd } from "@/lib/format";
import { DEMO_SEQUENCE, MODELS, PRESETS } from "@/lib/presets";
import type { CacheMode, ChatResult } from "@/lib/types";

interface Row extends ChatResult { id: number; prompt: string; namespace: string }

export default function PlaygroundPage() {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const namespaces = useQuery({ queryKey: ["namespaces"], queryFn: () => api.namespaces() });
  const [namespace, setNamespace] = useState("playground");
  const [model, setModel] = useState(MODELS[0]!);
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState(PRESETS[0]!.prompt);
  const [mode, setMode] = useState<CacheMode>("");
  const [rows, setRows] = useState<Row[]>([]);
  const [seq, setSeq] = useState(0);
  const last = rows[0];

  async function ask(text: string): Promise<Row> {
    const messages = [...(system.trim() ? [{ role: "system", content: system.trim() }] : []), { role: "user", content: text }];
    const res = await api.chat({ model, messages }, { namespace, cache: mode });
    const row: Row = { ...res, id: Date.now() + Math.random(), prompt: text, namespace };
    setRows((r) => [row, ...r].slice(0, 30));
    void qc.invalidateQueries();
    return row;
  }

  const send = useMutation({ mutationFn: () => ask(prompt), onError: (e) => toast("error", e.message) });
  const demo = useMutation({
    mutationFn: async () => {
      setSeq(0);
      for (const [i, q] of DEMO_SEQUENCE.entries()) {
        setSeq(i + 1);
        await ask(q);
      }
    },
    onError: (e) => toast("error", e.message),
  });

  const hits = rows.filter((r) => r.result === "HIT" || r.result === "COALESCED");
  const misses = rows.filter((r) => r.result === "MISS");
  const avg = (xs: Row[]) => (xs.length ? Math.round(xs.reduce((n, r) => n + r.elapsedMs, 0) / xs.length) : null);
  const maxMs = Math.max(1, ...rows.map((r) => r.elapsedMs));

  return (
    <>
      <PageHeader
        title="Playground"
        description="Send requests through the cache and see, per request, whether it was served from cache, how similar it was, and what it saved."
        actions={<Button onClick={() => demo.mutate()} loading={demo.isPending} data-testid="run-demo"><Play className="size-3.5" />{demo.isPending ? `Running ${seq}/${DEMO_SEQUENCE.length}` : "Run demo sequence"}</Button>}
      />
      <div className="grid gap-5 lg:grid-cols-5">
        <form className="card space-y-4 p-5 lg:col-span-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }} aria-label="Ask">
          <div className="flex flex-wrap gap-1.5" aria-label="Example prompts">
            {PRESETS.map((p) => (
              <button type="button" key={p.label} onClick={() => setPrompt(p.prompt)} title={p.hint} data-testid={`preset-${p.label}`}
                className="rounded-md border border-line px-2 py-1 text-xs text-muted transition hover:border-subtle/60 hover:text-fg">{p.label}</button>
            ))}
          </div>
          <Field label="Prompt"><Textarea rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} name="prompt" className="!font-sans !text-[13px]" /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Namespace"><Input value={namespace} onChange={(e) => setNamespace(e.target.value)} list="ns-list" name="namespace" pattern="[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,63}" required />
              <datalist id="ns-list">{(namespaces.data ?? []).map((n) => <option key={n.name} value={n.name} />)}</datalist></Field>
            <Field label="Model"><Select value={model} onChange={(e) => setModel(e.target.value)} name="model">{MODELS.map((m) => <option key={m}>{m}</option>)}</Select></Field>
          </div>
          <Field label="System prompt (optional)" hint="A different system prompt is a different safety scope: it never shares answers."><Input value={system} onChange={(e) => setSystem(e.target.value)} placeholder="You are a helpful support agent" name="system" /></Field>
          <Field label="Cache mode">
            <Select value={mode} onChange={(e) => setMode(e.target.value as CacheMode)} name="mode">
              <option value="">Normal: read and write</option>
              <option value="bypass">Bypass: skip the cache entirely</option>
              <option value="refresh">Refresh: skip the read, replace the entry</option>
              <option value="no-store">No-store: read only</option>
              <option value="only-if-cached">Only-if-cached: never call the provider</option>
            </Select>
          </Field>
          <div className="flex items-center justify-between border-t border-line pt-4">
            <button type="button" onClick={() => setRows([])} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg"><Eraser className="size-3.5" />Clear log</button>
            <Button type="submit" variant="primary" loading={send.isPending} disabled={!prompt.trim()}><Send className="size-3.5" />Send</Button>
          </div>
        </form>

        <div className="space-y-5 lg:col-span-3">
          <div className="card p-5" data-testid="result">
            {!last ? (
              <div className="py-10 text-center"><Zap className="mx-auto mb-2 size-6 text-subtle" /><p className="font-medium">Send a prompt to see the cache work</p><p className="mt-1 text-[13px] text-muted">Try “Reset password”, then its “Paraphrase”, then the “Look-alike”.</p></div>
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <ResultBadge result={last.result} type={last.type} />
                  {last.similarity !== null && <span className="text-[13px] text-muted">similarity <b className="tabular-nums text-fg">{last.similarity.toFixed(3)}</b></span>}
                  <span className="text-[13px] text-muted">you waited <b className="tabular-nums text-fg">{formatDuration(last.elapsedMs)}</b></span>
                  {last.savedUsd !== null && <span className="text-[13px] text-completed">saved {formatUsd(last.savedUsd)} · {last.savedTokens} tokens{last.savedMs ? ` · ${formatDuration(last.savedMs)}` : ""}</span>}
                </div>
                {last.rejectedReason && <p className="mb-3 rounded-md border border-waiting/30 bg-waiting/10 px-3 py-2 text-[13px] text-waiting" data-testid="guard-note">A near match ({last.rejectedSimilarity?.toFixed(3)}) was rejected: <b>{last.rejectedReason}</b>. The provider answered instead.</p>}
                {last.error ? <p role="alert" className="rounded-md border border-failed/30 bg-failed/10 px-3 py-2 text-[13px] text-failed">{last.error}</p>
                  : <p className="whitespace-pre-wrap rounded-lg border border-line bg-bg p-3.5 text-[13px] leading-relaxed" data-testid="answer">{last.content}</p>}
              </>
            )}
          </div>

          {rows.length > 0 && (
            <div className="card">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
                <h2 className="text-[13px] font-semibold">This session</h2>
                <span className="text-xs text-muted" data-testid="session-summary">
                  {hits.length} of {rows.length} from cache
                  {avg(hits) !== null && avg(misses) !== null ? ` · cache ${formatDuration(avg(hits))} vs provider ${formatDuration(avg(misses))}` : ""}
                </span>
              </div>
              <ul className="divide-y divide-line/60" data-testid="log">
                {rows.map((r) => (
                  <li key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-2.5 text-[13px]" data-testid="log-row" data-result={r.result}>
                    <span className="truncate" title={r.prompt}>{r.prompt}</span>
                    <ResultBadge result={r.result} type={r.type} />
                    <div className="h-1.5 overflow-hidden rounded-full bg-raised"><div className={cn("h-full rounded-full", r.result === "HIT" || r.result === "COALESCED" ? "bg-completed" : "bg-waiting")} style={{ width: `${Math.max(2, (r.elapsedMs / maxMs) * 100)}%` }} /></div>
                    <span className="text-right text-xs tabular-nums text-muted">{formatDuration(r.elapsedMs)}{r.savedUsd ? ` · ${formatUsd(r.savedUsd)}` : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
