"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Plus, ShieldOff } from "lucide-react";
import { useState } from "react";
import { useApi, useConnection, useToast } from "@/components/providers";
import { Modal } from "@/components/ui/overlays";
import { Button, ErrorBanner, Field, Input, PageHeader } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { formatTime, relativeTime } from "@/lib/format";
import type { ApiKeyCreated } from "@/lib/types";

function ApiKeys() {
  const api = useApi();
  const toast = useToast();
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: () => api.apiKeys(), retry: false });
  const scopes = useQuery({ queryKey: ["api-key-scopes"], queryFn: () => api.scopes(), retry: false });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [namespace, setNamespace] = useState("");
  const [picked, setPicked] = useState<string[]>(["proxy:use"]);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const create = useMutation({
    mutationFn: () => api.createApiKey(name.trim(), picked, namespace.trim() || undefined),
    onSuccess: (k) => { setCreated(k); setOpen(false); setName(""); setNamespace(""); void qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (e) => toast("error", e.message),
  });
  const revoke = useMutation({
    mutationFn: (prefix: string) => api.revokeApiKey(prefix),
    onSuccess: () => { toast("success", "Key revoked"); void qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (e) => toast("error", e.message),
  });

  if (keys.error instanceof ApiError && keys.error.status === 403) {
    return <p className="text-[13px] text-muted">The key you are connected with cannot manage API keys (<code className="font-mono">keys:admin</code> scope).</p>;
  }
  const toggle = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]));

  return (
    <>
      {keys.error && <ErrorBanner error={keys.error} />}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[720px] text-left text-[13px]">
          <thead><tr className="border-b border-line bg-raised/40">{["Name", "Scopes", "Namespace", "Created", "Last used", ""].map((h) => <th key={h} className="label px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {keys.data?.map((k) => (
              <tr key={k.prefix} className="border-b border-line/60 last:border-0" data-testid="key-row">
                <td className="px-3 py-2.5"><div className="font-medium">{k.name}{k.revoked && <span className="ml-2 text-xs text-failed">revoked</span>}</div><div className="font-mono text-[11px] text-subtle">sc_{k.prefix}_…</div></td>
                <td className="px-3 py-2.5"><div className="flex flex-wrap gap-1">{k.scopes.map((s) => <span key={s} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px] text-muted">{s}</span>)}</div></td>
                <td className="px-3 py-2.5 text-muted">{k.namespace ?? "any"}</td>
                <td className="px-3 py-2.5 text-muted" title={formatTime(k.created_at)}>{relativeTime(k.created_at)}</td>
                <td className="px-3 py-2.5 text-muted">{k.last_used_at ? relativeTime(k.last_used_at) : "never"}</td>
                <td className="px-3 py-2.5 text-right">{!k.revoked && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(k.prefix)} aria-label={`Revoke ${k.name}`}><ShieldOff className="size-3.5" />Revoke</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3"><Button onClick={() => setOpen(true)}><Plus className="size-3.5" />Create API key</Button></div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create API key"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={create.isPending} disabled={!name.trim() || picked.length === 0} onClick={() => create.mutate()}>Create key</Button></>}>
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="support-bot" autoFocus name="keyName" /></Field>
        <Field label="Bind to a namespace (optional)" hint="A bound key can only read and write its own namespace: one key per tenant."><Input value={namespace} onChange={(e) => setNamespace(e.target.value)} placeholder="acme-support" name="keyNamespace" /></Field>
        <fieldset>
          <legend className="label mb-2">Scopes</legend>
          <div className="grid grid-cols-2 gap-2">
            {(scopes.data ?? []).filter((s) => s !== "*").map((s) => (
              <label key={s} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[13px]">
                <input type="checkbox" checked={picked.includes(s)} onChange={() => toggle(s)} className="accent-[rgb(var(--accent))]" />
                <span className="font-mono text-xs">{s}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </Modal>

      <Modal open={!!created} onClose={() => setCreated(null)} title="Copy your new key" footer={<Button variant="primary" onClick={() => setCreated(null)}>Done</Button>}>
        <p className="text-[13px] text-muted">This is the only time the key is shown. Use it as the API key of any OpenAI SDK, with this API as the base URL.</p>
        <div className="flex items-center gap-2 rounded-lg border border-line bg-bg p-3">
          <code className="min-w-0 flex-1 break-all font-mono text-xs" data-testid="new-key">{created?.key}</code>
          <Button size="sm" onClick={async () => { await navigator.clipboard?.writeText(created?.key ?? ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}{copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </Modal>
    </>
  );
}

export default function SettingsPage() {
  const { conn, disconnect } = useConnection();
  return (
    <>
      <PageHeader title="Settings" description="Connection details and API keys." />
      <div className="space-y-5">
        <section className="card p-5">
          <h2 className="mb-4 flex items-center gap-2 text-[13px] font-semibold"><KeyRound className="size-4 text-subtle" />Connection</h2>
          <dl className="grid gap-4 text-[13px] sm:grid-cols-2">
            <div><dt className="label">API URL</dt><dd className="mt-1 font-mono">{conn?.apiUrl}</dd></div>
            <div><dt className="label">API key</dt><dd className="mt-1 font-mono text-muted">{conn ? `${conn.apiKey.slice(0, 11)}${"•".repeat(12)}` : ""}</dd></div>
          </dl>
          <div className="mt-4 rounded-lg border border-line bg-bg p-3 font-mono text-xs leading-relaxed text-muted">
            <div className="label mb-1 !font-sans">Use it from the OpenAI SDK</div>
            client = OpenAI(base_url=&quot;{conn?.apiUrl}/v1&quot;, api_key=&quot;sc_…&quot;)
          </div>
          <div className="mt-4"><Button variant="danger" onClick={disconnect}>Disconnect</Button></div>
        </section>
        <section className="card p-5"><h2 className="mb-4 text-[13px] font-semibold">API keys</h2><ApiKeys /></section>
      </div>
    </>
  );
}
