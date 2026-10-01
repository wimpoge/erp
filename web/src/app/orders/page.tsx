"use client";

import { useCallback, useEffect, useState } from "react";
import { api, localTime, Order, rupiah } from "@/lib/api";
import StatusBadge from "../status-badge";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [open, setOpen] = useState<Order | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Order[]>(`/api/orders?limit=100${filter ? `&push_status=${filter}` : ""}`)
      .then(setOrders)
      .catch((e) => setMessage(e.message));
  }, [filter]);

  useEffect(load, [load]);

  async function pushPending() {
    const r = await api<{ tried: number; sent: number; pending: number; failed: number }>("/api/orders/push-pending", {
      method: "POST",
    });
    setMessage(`Retried ${r.tried} due order(s): ${r.sent} sent, ${r.pending} still pending, ${r.failed} failed.`);
    load();
  }

  async function pushOne(id: number) {
    setOpen(await api<Order>(`/api/orders/${id}/push`, { method: "POST" }));
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-lg font-semibold">Orders</h1>
        <select
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">All push states</option>
          <option value="pending">Pending</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
        </select>
        <button onClick={pushPending} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white">
          Retry due pushes
        </button>
      </div>
      {message && <p className="rounded-md bg-sky-50 px-3 py-2 text-sm text-sky-800">{message}</p>}

      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Number</th>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Customer</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2">ERP push</th>
              <th className="px-3 py-2">ERP number</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {orders.map((o) => (
              <tr
                key={o.id}
                className="cursor-pointer hover:bg-slate-50"
                onClick={() => api<Order>(`/api/orders/${o.id}`).then(setOpen)}
              >
                <td className="px-3 py-2 font-mono text-xs">{o.number}</td>
                <td className="px-3 py-2 text-slate-600">{localTime(o.created_at)}</td>
                <td className="px-3 py-2">{o.customer ?? <span className="text-slate-400">walk-in</span>}</td>
                <td className="px-3 py-2 text-right tabular-nums">{rupiah(o.total)}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={o.push_status} />
                  {o.push_attempts > 1 && <span className="ml-1 text-xs text-slate-500">×{o.push_attempts}</span>}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{o.erp_number ?? "—"}</td>
              </tr>
            ))}
            {orders.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-400">
                  No orders yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="fixed inset-0 z-20 flex justify-end bg-slate-900/30" onClick={() => setOpen(null)}>
          <div className="h-full w-full max-w-md space-y-4 overflow-y-auto bg-white p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-sm font-semibold">{open.number}</p>
                <p className="text-xs text-slate-500">external id {open.external_id}</p>
              </div>
              <StatusBadge status={open.push_status} />
            </div>
            <ul className="space-y-1 text-sm">
              {open.lines?.map((l) => (
                <li key={l.product_id} className="flex justify-between gap-2">
                  <span className="truncate">
                    {l.qty} × {l.name}
                  </span>
                  <span className="tabular-nums">{rupiah(l.line_total)}</span>
                </li>
              ))}
            </ul>
            <p className="text-sm">
              Total <b>{rupiah(open.total)}</b> · paid {open.payments?.map((p) => `${p.method} ${rupiah(p.amount)}`).join(", ")}
            </p>
            <div>
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Push attempts</h2>
              <ol className="space-y-1 text-xs">
                {open.push_log?.map((a) => (
                  <li key={a.attempt} className={a.ok ? "text-emerald-700" : "text-rose-700"}>
                    #{a.attempt} {localTime(a.at)} · {a.ok ? "ok" : `${a.status_code ?? "network"}: ${a.error}`}
                  </li>
                ))}
                {open.push_log?.length === 0 && <li className="text-slate-400">none yet</li>}
              </ol>
              {open.next_push_at && <p className="mt-1 text-xs text-slate-500">Next retry {localTime(open.next_push_at)}</p>}
            </div>
            {open.push_status !== "sent" && (
              <button onClick={() => pushOne(open.id)} className="w-full rounded-lg bg-slate-900 py-2 text-sm text-white">
                Push now
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
