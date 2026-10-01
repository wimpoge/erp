"use client";

import { Banknote, CreditCard, Printer, QrCode, Receipt, Search, TrendingUp } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import PrintableReceipt from "@/components/receipt";
import SyncStatus from "@/components/sync-status";
import { useToast } from "@/components/toast";
import { Button, Dialog, EmptyState, Spinner, inputClass } from "@/components/ui";
import { api, dateTime, errorMessage, Order, rupiah, SalesSummary, startOfToday, timeOnly } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function SalesPage() {
  const { location } = useSession();
  const toast = useToast();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Order | null>(null);

  useEffect(() => {
    if (!location) return;
    const since = encodeURIComponent(startOfToday());
    const timer = setTimeout(() => {
      const search = q.trim() ? `&q=${encodeURIComponent(q.trim())}` : "";
      Promise.all([
        api<Order[]>(`/api/orders?location_id=${location.id}&since=${since}&limit=500${search}`),
        api<SalesSummary>(`/api/orders/summary?location_id=${location.id}&since=${since}`),
      ])
        .then(([o, s]) => {
          setOrders(o);
          setSummary(s);
        })
        .catch((e) => toast(errorMessage(e), "error"));
    }, 200);
    return () => clearTimeout(timer);
  }, [location, q, toast]);

  async function show(id: number) {
    try {
      setOpen(await api<Order>(`/api/orders/${id}`));
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  return (
    <>
      <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6 print:hidden">
        <div>
          <h1 className="text-xl font-semibold">Today&apos;s sales</h1>
          <p className="text-sm text-slate-500">{location?.name}</p>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Tile icon={<Receipt />} label="Sales" value={summary ? String(summary.count) : "…"} />
          <Tile icon={<TrendingUp />} label="Revenue" value={summary ? rupiah(summary.revenue) : "…"} strong />
          <Tile icon={<Banknote />} label="Cash in drawer" value={summary ? rupiah(summary.by_method.cash ?? 0) : "…"} />
          <Tile icon={<CreditCard />} label="Card" value={summary ? rupiah(summary.by_method.card ?? 0) : "…"} />
          <Tile icon={<QrCode />} label="QRIS" value={summary ? rupiah(summary.by_method.qris ?? 0) : "…"} />
        </div>

        <div className="relative max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            className={`${inputClass} pl-10`}
            placeholder="Find by receipt number or customer"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
          {orders === null ? (
            <Spinner />
          ) : orders.length === 0 ? (
            <EmptyState icon={<Receipt className="h-12 w-12" />} title={q ? "No sale matches your search" : "No sales yet today"}>
              {!q && "Completed sales will appear here."}
            </EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100">
              {orders.map((o) => (
                <li key={o.id}>
                  <button onClick={() => show(o.id)} className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-slate-50 sm:grid-cols-[4rem_1fr_8rem_8rem_7rem]">
                    <span className="text-sm tabular-nums text-slate-500">{timeOnly(o.created_at)}</span>
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-sm">{o.number}</span>
                      <span className="block truncate text-xs text-slate-500">
                        {o.customer ?? "Walk-in"} · {o.items} item(s){o.cashier ? ` · ${o.cashier}` : ""}
                      </span>
                    </span>
                    <span className="text-right font-semibold tabular-nums">{rupiah(o.total)}</span>
                    <span className="hidden text-sm text-slate-500 sm:block">{o.register}</span>
                    <span className="col-span-3 sm:col-span-1">
                      <SyncStatus order={o} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Dialog open={open !== null} onClose={() => setOpen(null)} title={open ? `Receipt ${open.number}` : ""}>
        {open && (
          <div className="space-y-4">
            <p className="text-sm text-slate-500">
              {dateTime(open.created_at)} · {open.register} · {open.cashier}
              {open.customer && ` · ${open.customer}`}
            </p>
            <ul className="space-y-2 text-sm">
              {open.lines?.map((l) => (
                <li key={l.product_id} className="flex justify-between gap-3">
                  <span>
                    {l.qty} × {l.name}
                  </span>
                  <span className="tabular-nums">{rupiah(l.line_total)}</span>
                </li>
              ))}
            </ul>
            <div className="space-y-1 border-t border-slate-200 pt-3 text-sm">
              {open.discount > 0 && <Row label="Member discount" value={`−${rupiah(open.discount)}`} />}
              <Row label="Total" value={rupiah(open.total)} strong />
              {open.payments?.map((p, i) => (
                <Row key={i} label={`Paid (${p.method.toUpperCase()})`} value={rupiah(p.amount)} />
              ))}
              <Row label="Change" value={rupiah(open.change)} />
            </div>
            <SyncStatus order={open} long />
            <Button variant="secondary" className="w-full" onClick={() => window.print()}>
              <Printer className="h-4 w-4" /> Print receipt again
            </Button>
          </div>
        )}
      </Dialog>
      <PrintableReceipt order={open} />
    </>
  );
}

function Tile({ icon, label, value, strong }: { icon: ReactNode; label: string; value: string; strong?: boolean }) {
  return (
    <div className={`rounded-xl p-4 shadow-sm ring-1 ${strong ? "bg-slate-900 text-white ring-slate-900" : "bg-white ring-slate-200"}`}>
      <div className={`mb-2 h-5 w-5 ${strong ? "text-sky-400" : "text-slate-400"} [&>svg]:h-5 [&>svg]:w-5`}>{icon}</div>
      <p className={`text-xs ${strong ? "text-slate-300" : "text-slate-500"}`}>{label}</p>
      <p className="text-lg font-bold tabular-nums">{value}</p>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? "text-base font-semibold" : "text-slate-600"}`}>
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
