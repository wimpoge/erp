"use client";

import { CloudDownload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/toast";
import { Badge, Button, EmptyState } from "@/components/ui";
import { api, dateTime, errorMessage, SyncEvent, SyncRun, SyncState } from "@/lib/api";

const LABELS: Record<string, string> = {
  customer_groups: "Customer groups",
  locations: "Stores",
  registers: "Registers",
  customers: "Customers",
  products: "Products & prices",
};
const label = (key: string) => LABELS[key] ?? (key.startsWith("stock:") ? `Stock ${key.slice(6)}` : key);

const tone = (status: string) =>
  status === "ok" ? "green" : status === "failed" ? "red" : status === "partial" || status === "skipped" ? "amber" : "slate";
const statusText: Record<string, string> = { ok: "Up to date", partial: "Some rows failed", failed: "Failed", skipped: "Kept (empty answer)", running: "Running" };

const fetchOverview = () => Promise.all([api<SyncRun[]>("/api/sync/runs"), api<SyncState[]>("/api/sync/state")]);

export default function SyncPage() {
  const toast = useToast();
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [state, setState] = useState<SyncState[]>([]);
  const [selected, setSelected] = useState<SyncRun | null>(null);
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [busy, setBusy] = useState(false);

  const show = useCallback(([r, s]: [SyncRun[], SyncState[]]) => {
    setRuns(r);
    setState(s);
    setSelected((cur) => cur ?? r[0] ?? null);
  }, []);

  useEffect(() => {
    fetchOverview()
      .then(show)
      .catch((e) => toast(errorMessage(e), "error"));
  }, [show, toast]);

  useEffect(() => {
    if (!selected) return;
    // Inserts on a first sync are just noise; show what changed or went wrong.
    Promise.all(["update", "deactivate", "delete", "skipped", "error"].map((a) =>
      api<SyncEvent[]>(`/api/sync/runs/${selected.id}/events?action=${a}&limit=500`),
    )).then((lists) => setEvents(lists.flat().sort((a, b) => a.id - b.id)));
  }, [selected]);

  async function syncNow() {
    setBusy(true);
    try {
      const run = await api<SyncRun>("/api/sync", { method: "POST" });
      setSelected(run);
      show(await fetchOverview());
      toast(run.status === "ok" ? "Products, prices, stock and customers are up to date." : "Sync finished with problems: see below.", run.status === "ok" ? "success" : "error");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto max-w-xl text-sm text-slate-600">
          Stores, products, prices, stock and customers come from head office. Sync to pull the latest changes.
        </p>
        <Button onClick={syncNow} loading={busy}>
          <CloudDownload className="h-4 w-4" /> {busy ? "Syncing…" : "Sync now"}
        </Button>
      </div>

      {state.length === 0 ? (
        <div className="rounded-xl bg-white ring-1 ring-slate-200">
          <EmptyState icon={<CloudDownload className="h-12 w-12" />} title="Never synced">
            Press Sync now to load stores, products and customers from head office.
          </EmptyState>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {state.map((s) => (
            <div key={s.key} className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">{label(s.key)}</p>
                <Badge tone={tone(s.last_status)}>{statusText[s.last_status] ?? s.last_status}</Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {s.rows} rows · {s.last_synced_at ? `updated ${dateTime(s.last_synced_at)}` : "not fully synced yet"}
              </p>
            </div>
          ))}
        </div>
      )}

      {runs.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
          <ol className="space-y-1">
            <p className="mb-2 text-xs font-medium text-slate-500">History</p>
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => setSelected(r)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${
                    selected?.id === r.id ? "bg-white shadow-sm ring-1 ring-slate-200" : "hover:bg-white/60"
                  }`}
                >
                  <span>{dateTime(r.started_at)}</span>
                  <Badge tone={tone(r.status)}>{r.status === "ok" ? "OK" : r.status}</Badge>
                </button>
              </li>
            ))}
          </ol>

          {selected && (
            <div className="min-w-0 space-y-4">
              <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs text-slate-500">
                    <tr>
                      <th className="px-4 py-2 font-medium">List</th>
                      <th className="px-4 py-2 text-right font-medium">New</th>
                      <th className="px-4 py-2 text-right font-medium">Changed</th>
                      <th className="px-4 py-2 text-right font-medium">Removed</th>
                      <th className="px-4 py-2 text-right font-medium">Errors</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 tabular-nums">
                    {Object.entries(selected.summary).map(([key, s]) => (
                      <tr key={key}>
                        <td className="px-4 py-2">
                          {label(key)}
                          {s.skipped && <span className="ml-2 text-xs text-amber-700">head office sent nothing, kept ours</span>}
                          {s.error && <span className="ml-2 text-xs text-rose-700">{s.error}</span>}
                        </td>
                        <td className="px-4 py-2 text-right">{s.inserted ?? "–"}</td>
                        <td className="px-4 py-2 text-right">{s.updated ?? "–"}</td>
                        <td className="px-4 py-2 text-right">{s.removed ?? "–"}</td>
                        <td className={`px-4 py-2 text-right ${s.errors ? "font-semibold text-rose-700" : ""}`}>{s.errors ?? "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
                <p className="mb-2 text-xs font-medium text-slate-500">Changes and problems in this sync</p>
                {events.length === 0 ? (
                  <p className="text-sm text-slate-500">Nothing changed apart from new rows.</p>
                ) : (
                  <ul className="space-y-1 text-sm">
                    {events.map((e) => (
                      <li key={e.id} className="flex gap-2">
                        <Badge tone={e.action === "error" ? "red" : e.action === "skipped" ? "amber" : "blue"}>{e.action}</Badge>
                        <span className="text-slate-500">{label(e.table)}</span>
                        <span className="min-w-0 truncate">{e.message}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
