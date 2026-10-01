"use client";

import { CheckCircle2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import SyncStatus from "@/components/sync-status";
import { useToast } from "@/components/toast";
import { Button, Dialog, EmptyState, Spinner } from "@/components/ui";
import { api, dateTime, errorMessage, Order, rupiah } from "@/lib/api";

type Filter = "attention" | "all";

async function fetchQueue(filter: Filter): Promise<Order[]> {
  if (filter === "all") return api<Order[]>("/api/orders?limit=200");
  const [failed, pending] = await Promise.all([
    api<Order[]>("/api/orders?push_status=failed"),
    api<Order[]>("/api/orders?push_status=pending"),
  ]);
  return [...failed, ...pending];
}

export default function SalesQueuePage() {
  const toast = useToast();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [filter, setFilter] = useState<Filter>("attention");
  const [open, setOpen] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => setOrders(await fetchQueue(filter)), [filter]);

  useEffect(() => {
    fetchQueue(filter)
      .then(setOrders)
      .catch((e) => toast(errorMessage(e), "error"));
  }, [filter, toast]);

  async function retryDue() {
    setBusy(true);
    try {
      const r = await api<{ tried: number; sent: number; pending: number; failed: number }>("/api/orders/push-pending", { method: "POST" });
      toast(
        r.tried === 0 ? "Nothing is due for a retry yet." : `Sent ${r.sent} of ${r.tried}. ${r.pending} still waiting, ${r.failed} need a check.`,
        r.pending || r.failed ? "info" : "success",
      );
      await load();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  async function pushNow(id: number) {
    setBusy(true);
    try {
      const order = await api<Order>(`/api/orders/${id}/push`, { method: "POST" });
      setOpen(order);
      toast(order.push_status === "sent" ? "Sent to head office." : "Head office still didn't accept it.", order.push_status === "sent" ? "success" : "error");
      await load();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto max-w-xl text-sm text-slate-600">
          Every sale is saved in the store first and then sent to head office. Sales that are still waiting, or that head
          office did not accept, show up here.
        </p>
        <div className="flex rounded-lg bg-white p-1 ring-1 ring-slate-200">
          {(["attention", "all"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-3 py-1.5 text-sm ${filter === f ? "bg-slate-900 text-white" : "text-slate-600"}`}
            >
              {f === "attention" ? "Not sent yet" : "All sales"}
            </button>
          ))}
        </div>
        <Button onClick={retryDue} loading={busy} variant="secondary">
          <RefreshCw className="h-4 w-4" /> Retry waiting sales
        </Button>
      </div>

      <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        {orders === null ? (
          <Spinner />
        ) : orders.length === 0 ? (
          <EmptyState icon={<CheckCircle2 className="h-12 w-12 text-emerald-400" />} title="All sales reached head office">
            Nothing is waiting.
          </EmptyState>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Receipt</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">Store</th>
                <th className="px-4 py-2 text-right font-medium">Total</th>
                <th className="px-4 py-2 font-medium">Head office</th>
                <th className="hidden px-4 py-2 font-medium md:table-cell">Tries</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.map((o) => (
                <tr key={o.id} className="cursor-pointer hover:bg-slate-50" onClick={() => api<Order>(`/api/orders/${o.id}`).then(setOpen)}>
                  <td className="px-4 py-2.5">
                    <p className="font-mono">{o.number}</p>
                    <p className="text-xs text-slate-500">{dateTime(o.created_at)}</p>
                  </td>
                  <td className="hidden px-4 py-2.5 sm:table-cell">{o.location_name}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{rupiah(o.total)}</td>
                  <td className="px-4 py-2.5">
                    <SyncStatus order={o} />
                  </td>
                  <td className="hidden px-4 py-2.5 tabular-nums md:table-cell">{o.push_attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Dialog open={open !== null} onClose={() => setOpen(null)} title={open?.number}>
        {open && (
          <div className="space-y-4 text-sm">
            <SyncStatus order={open} long />
            {open.last_push_error && (
              <p className="rounded-lg bg-rose-50 p-3 font-mono text-xs text-rose-800">{open.last_push_error}</p>
            )}
            <div>
              <p className="mb-1 font-medium">Attempts</p>
              <ol className="space-y-1 text-xs">
                {open.push_log?.map((a) => (
                  <li key={a.attempt} className={a.ok ? "text-emerald-700" : "text-slate-600"}>
                    #{a.attempt} · {dateTime(a.at)} · {a.ok ? "accepted" : `${a.status_code ?? "no connection"}`}
                  </li>
                ))}
                {open.push_log?.length === 0 && <li className="text-slate-400">Not tried yet.</li>}
              </ol>
              {open.next_push_at && <p className="mt-2 text-xs text-slate-500">Next automatic try: {dateTime(open.next_push_at)}</p>}
            </div>
            <p className="text-xs text-slate-500">Reference id {open.external_id}: head office uses it to ignore duplicates.</p>
            {open.push_status !== "sent" && (
              <Button className="w-full" loading={busy} onClick={() => pushNow(open.id)}>
                Send now
              </Button>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
}
