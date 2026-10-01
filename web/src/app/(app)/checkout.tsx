"use client";

import { Banknote, CheckCircle2, CreditCard, Printer, QrCode } from "lucide-react";
import { useState } from "react";
import { Button, Dialog, Kbd, inputClass } from "@/components/ui";
import { Customer, Order, rupiah } from "@/lib/api";

export type Method = "cash" | "card" | "qris";

const METHODS: { id: Method; label: string; icon: typeof Banknote }[] = [
  { id: "cash", label: "Cash", icon: Banknote },
  { id: "card", label: "Debit / credit card", icon: CreditCard },
  { id: "qris", label: "QRIS", icon: QrCode },
];

/** Exact amount plus the next amounts a customer is likely to hand over. */
function cashSuggestions(total: number): number[] {
  const out = new Set<number>([total]);
  for (const step of [10_000, 20_000, 50_000, 100_000]) {
    out.add(Math.ceil(total / step) * step);
  }
  return [...out].filter((v) => v >= total).sort((a, b) => a - b).slice(0, 5);
}

export function CheckoutDialog({
  open,
  onClose,
  total,
  subtotal,
  discount,
  items,
  customer,
  onComplete,
}: {
  open: boolean;
  onClose: () => void;
  total: number;
  subtotal: number;
  discount: number;
  items: number;
  customer: Customer | null;
  onComplete: (method: Method, amount: number) => Promise<void>;
}) {
  const [method, setMethod] = useState<Method>("cash");
  const [cash, setCash] = useState("");
  const [busy, setBusy] = useState(false);

  const received = method === "cash" ? Number(cash || 0) : total;
  const change = received - total;
  const ready = received >= total && !busy;

  function close() {
    if (busy) return;
    setCash("");
    setMethod("cash");
    onClose();
  }

  async function complete() {
    if (!ready) return;
    setBusy(true);
    try {
      await onComplete(method, received);
      setCash("");
      setMethod("cash");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Payment" wide>
      <form
        className="grid gap-6 md:grid-cols-[1fr_1.2fr]"
        onSubmit={(e) => {
          e.preventDefault();
          complete();
        }}
        onKeyDown={(e) => {
          // Enter completes the sale even when focus is on a payment-method button.
          if (e.key === "Enter" && (e.target as HTMLElement).tagName === "BUTTON") {
            e.preventDefault();
            complete();
          }
        }}
      >
        <div className="space-y-3 rounded-xl bg-slate-50 p-4">
          <p className="text-sm text-slate-500">{items} item(s)</p>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span>Subtotal</span>
              <span className="tabular-nums">{rupiah(subtotal)}</span>
            </div>
            {discount > 0 && (
              <div className="flex justify-between text-emerald-700">
                <span>
                  {customer?.group} discount {customer?.discount_rate}%
                </span>
                <span className="tabular-nums">−{rupiah(discount)}</span>
              </div>
            )}
          </div>
          <div className="border-t border-slate-200 pt-3">
            <p className="text-sm text-slate-500">Amount due</p>
            <p className="text-4xl font-bold tabular-nums tracking-tight">{rupiah(total)}</p>
          </div>
          {customer && <p className="text-sm text-slate-600">Customer: {customer.name}</p>}
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {METHODS.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                onClick={() => setMethod(id)}
                className={`flex flex-col items-center gap-1.5 rounded-xl border-2 p-3 text-sm font-medium transition ${
                  method === id ? "border-sky-500 bg-sky-50 text-sky-900" : "border-slate-200 text-slate-600 hover:border-slate-300"
                }`}
              >
                <Icon className="h-6 w-6" />
                {label}
              </button>
            ))}
          </div>

          {method === "cash" ? (
            <div className="space-y-3">
              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-slate-700">Cash received</span>
                <input
                  autoFocus
                  inputMode="numeric"
                  className={`${inputClass} h-14 text-right text-2xl font-semibold tabular-nums`}
                  placeholder="0"
                  value={cash ? Number(cash).toLocaleString("id-ID") : ""}
                  onChange={(e) => setCash(e.target.value.replace(/\D/g, "").slice(0, 10))}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                {cashSuggestions(total).map((v) => (
                  <button
                    type="button"
                    key={v}
                    onClick={() => setCash(String(v))}
                    className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium tabular-nums hover:bg-slate-200"
                  >
                    {v === total ? "Exact" : rupiah(v)}
                  </button>
                ))}
              </div>
              <div
                className={`rounded-xl p-4 ${
                  !cash ? "bg-slate-50 text-slate-400" : change >= 0 ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-700"
                }`}
              >
                <p className="text-sm">{!cash || change >= 0 ? "Change to give" : "Still short"}</p>
                <p className="text-3xl font-bold tabular-nums">{rupiah(Math.abs(cash ? change : 0))}</p>
              </div>
            </div>
          ) : (
            <p className="rounded-xl bg-sky-50 p-4 text-sm text-sky-900">
              {method === "card"
                ? `Charge ${rupiah(total)} on the card terminal. Complete the sale once it is approved.`
                : `Show the QRIS code for ${rupiah(total)}. Complete the sale once the customer's payment is confirmed.`}
            </p>
          )}

          <Button type="submit" variant="success" size="xl" className="w-full" disabled={!ready} loading={busy}>
            Complete sale <Kbd>Enter</Kbd>
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function SaleDoneDialog({ order, onNewSale }: { order: Order | null; onNewSale: () => void }) {
  return (
    <Dialog open={order !== null} onClose={onNewSale}>
      {order && (
        <div className="space-y-5 text-center">
          <CheckCircle2 className="mx-auto h-14 w-14 text-emerald-500" />
          <div>
            <p className="text-lg font-semibold">Sale complete</p>
            <p className="font-mono text-sm text-slate-500">{order.number}</p>
          </div>
          {order.change > 0 ? (
            <div className="rounded-2xl bg-emerald-50 p-5">
              <p className="text-sm text-emerald-800">Give change</p>
              <p className="text-5xl font-bold tabular-nums text-emerald-700">{rupiah(order.change)}</p>
            </div>
          ) : (
            <p className="rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">
              Paid {rupiah(order.total)} by {order.payments?.[0]?.method.toUpperCase()}. No change.
            </p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" size="lg" onClick={() => window.print()}>
              <Printer className="h-5 w-5" /> Print receipt
            </Button>
            <Button size="lg" data-primary onClick={onNewSale}>
              New sale <Kbd>Enter</Kbd>
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
