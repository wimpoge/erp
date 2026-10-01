"use client";

import { useCallback, useEffect, useState } from "react";
import { api, localTime, SyncEvent, SyncRun, SyncState } from "@/lib/api";
import StatusBadge from "../status-badge";

const fetchOverview = () => Promise.all([api<SyncRun[]>("/api/sync/runs"), api<SyncState[]>("/api/sync/state")]);

export default function SyncPage() {
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [state, setState] = useState<SyncState[]>([]);
  const [selected, setSelected] = useState<SyncRun | null>(null);
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const show = useCallback(([r, s]: [SyncRun[], SyncState[]]) => {
    setRuns(r);
    setState(s);
    setSelected((cur) => cur ?? r[0] ?? null);
  }, []);

  useEffect(() => {
    fetchOverview()
      .then(show)
      .catch((e) => setError(String(e)));
  }, [show]);

  useEffect(() => {
    if (selected) api<SyncEvent[]>(`/api/sync/runs/${selected.id}/events?limit=1000`).then(setEvents);
  }, [selected]);

  async function syncNow() {
    setBusy(true);
    setError(null);
    try {
      const run = await api<SyncRun>("/api/sync", { method: "POST" });
      setSelected(run);
      show(await fetchOverview());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const changes = events.filter((e) => e.action !== "insert" || events.length < 60);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="mr-auto text-lg font-semibold">ERP sync</h1>
        <button disabled={busy} onClick={syncNow} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          {busy ? "Syncing…" : "Sync now"}
        </button>
      </div>
      {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

      <section className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {state.map((s) => (
          <div key={s.key} className="rounded-lg bg-white p-3 ring-1 ring-slate-200">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs">{s.key}</span>
              <StatusBadge status={s.last_status} />
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {s.rows} rows · {s.last_synced_at ? localTime(s.last_synced_at) : "never fully synced"}
            </p>
          </div>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <ol className="space-y-1">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => setSelected(r)}
                className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${
                  selected?.id === r.id ? "bg-white ring-1 ring-slate-300" : "hover:bg-white"
                }`}
              >
                <span>
                  Run #{r.id} <span className="text-xs text-slate-500">{localTime(r.started_at)}</span>
                </span>
                <StatusBadge status={r.status} />
              </button>
            </li>
          ))}
          {runs.length === 0 && <li className="text-sm text-slate-400">No runs yet: press Sync now.</li>}
        </ol>

        {selected && (
          <div className="min-w-0 space-y-4">
            <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">List</th>
                    <th className="px-3 py-2 text-right">Rows</th>
                    <th className="px-3 py-2 text-right">New</th>
                    <th className="px-3 py-2 text-right">Updated</th>
                    <th className="px-3 py-2 text-right">Removed</th>
                    <th className="px-3 py-2 text-right">Errors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 tabular-nums">
                  {Object.entries(selected.summary).map(([key, s]) => (
                    <tr key={key}>
                      <td className="px-3 py-1.5 font-mono text-xs">
                        {key}
                        {s.skipped && <span className="ml-2 text-amber-700">kept (ERP sent 0 rows)</span>}
                        {s.error && <span className="ml-2 text-rose-700">{s.error}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right">{s.rows ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">{s.inserted ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">{s.updated ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">{s.removed ?? "—"}</td>
                      <td className={`px-3 py-1.5 text-right ${s.errors ? "font-semibold text-rose-700" : ""}`}>{s.errors ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Events {changes.length < events.length && `(${events.length - changes.length} inserts hidden)`}
              </h2>
              <ul className="space-y-1 font-mono text-xs">
                {changes.map((e) => (
                  <li key={e.id} className={e.action === "error" ? "text-rose-700" : e.action === "skipped" ? "text-amber-700" : ""}>
                    {e.action.padEnd(10)} {e.table.padEnd(16)} {e.erp_public_id?.slice(0, 8) ?? ""} {e.message ?? ""}
                  </li>
                ))}
                {events.length === 0 && <li className="text-slate-400">No changes in this run.</li>}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
