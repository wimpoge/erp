"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, Customer, Location, Order, Product, rupiah } from "@/lib/api";
import StatusBadge from "./status-badge";

type CartLine = { product: Product; qty: number };
type Method = "cash" | "card" | "qris";

const STORE_KEY = "my-pos.till";

export default function Till() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [registerId, setRegisterId] = useState<number | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [method, setMethod] = useState<Method>("cash");
  const [tendered, setTendered] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<Order | null>(null);

  useEffect(() => {
    api<Location[]>("/api/locations")
      .then((locs) => {
        setLocations(locs);
        let saved: { locationId?: number; registerId?: number } = {};
        try {
          saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? "{}");
        } catch {}
        const loc = locs.find((l) => l.id === saved.locationId) ?? locs[0];
        if (loc) {
          setLocationId(loc.id);
          setRegisterId(loc.registers.find((r) => r.id === saved.registerId)?.id ?? loc.registers[0]?.id ?? null);
        }
      })
      .catch((e) => setError(`Cannot reach the POS API: ${e.message}`));
  }, []);

  useEffect(() => {
    if (locationId === null) return;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ locationId, registerId }));
    } catch {}
  }, [locationId, registerId]);

  const loadProducts = useCallback(() => {
    if (locationId === null) return;
    api<Product[]>(`/api/products?location_id=${locationId}&limit=500`).then(setProducts).catch((e) => setError(e.message));
  }, [locationId]);

  useEffect(loadProducts, [loadProducts]);

  const categories = useMemo(() => [...new Set(products.map((p) => p.category))].sort(), [products]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return products.filter(
      (p) =>
        (!category || p.category === category) &&
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || p.barcode === q),
    );
  }, [products, query, category]);

  const subtotal = cart.reduce((sum, l) => sum + l.qty * l.product.price, 0);
  const discount = Math.floor((subtotal * (customer?.discount_rate ?? 0)) / 100);
  const total = subtotal - discount;
  const paid = method === "cash" ? Number(tendered || 0) : total;
  const change = method === "cash" ? paid - total : 0;

  function add(product: Product) {
    setCart((lines) => {
      const line = lines.find((l) => l.product.id === product.id);
      if (!line) return [...lines, { product, qty: 1 }];
      if (line.qty >= product.on_hand) return lines;
      return lines.map((l) => (l === line ? { ...l, qty: l.qty + 1 } : l));
    });
  }

  function setQty(productId: number, qty: number) {
    setCart((lines) =>
      lines
        .map((l) => (l.product.id === productId ? { ...l, qty: Math.min(qty, l.product.on_hand) } : l))
        .filter((l) => l.qty > 0),
    );
  }

  function onSearchEnter() {
    // A barcode scanner types the code and presses Enter.
    const exact = products.find((p) => p.barcode === query.trim() || p.sku.toLowerCase() === query.trim().toLowerCase());
    if (exact && exact.on_hand > 0) {
      add(exact);
      setQuery("");
    }
  }

  async function pay() {
    if (!locationId || cart.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const order = await api<Order>("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          location_id: locationId,
          register_id: registerId,
          customer_id: customer?.id ?? null,
          lines: cart.map((l) => ({ product_id: l.product.id, qty: l.qty })),
          payments: [{ method, amount: paid }],
        }),
      });
      setReceipt(order);
      setCart([]);
      setCustomer(null);
      setTendered("");
      loadProducts();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const location = locations.find((l) => l.id === locationId);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <section className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={locationId ?? ""}
            onChange={(e) => {
              const loc = locations.find((l) => l.id === Number(e.target.value));
              setLocationId(loc?.id ?? null);
              setRegisterId(loc?.registers[0]?.id ?? null);
              setCart([]);
            }}
          >
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.code} · {l.name}
              </option>
            ))}
          </select>
          <select
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={registerId ?? ""}
            onChange={(e) => setRegisterId(Number(e.target.value))}
          >
            {location?.registers.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <input
            className="min-w-48 flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            placeholder="Search name, SKU, or scan barcode"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearchEnter()}
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {[null, ...categories].map((c) => (
            <button
              key={c ?? "all"}
              onClick={() => setCategory(c)}
              className={`rounded-full px-3 py-1 text-xs ${
                category === c ? "bg-slate-900 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"
              }`}
            >
              {c ?? "All"}
            </button>
          ))}
        </div>

        {locations.length === 0 && !error && (
          <p className="text-sm text-slate-500">No stores yet: run a sync on the ERP sync page first.</p>
        )}

        <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3">
          {visible.map((p) => {
            const inCart = cart.find((l) => l.product.id === p.id)?.qty ?? 0;
            const out = p.on_hand - inCart <= 0;
            return (
              <button
                key={p.id}
                disabled={out}
                onClick={() => add(p)}
                className="flex flex-col rounded-lg bg-white p-3 text-left ring-1 ring-slate-200 transition hover:ring-slate-400 disabled:opacity-40"
              >
                <span className="text-[11px] uppercase tracking-wide text-slate-400">{p.category}</span>
                <span className="mt-0.5 line-clamp-2 text-sm font-medium">{p.name}</span>
                <span className="mt-auto pt-2 text-sm font-semibold">{rupiah(p.price)}</span>
                <span className="text-xs text-slate-500">{p.on_hand - inCart} in stock</span>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="h-fit space-y-4 rounded-xl bg-white p-4 ring-1 ring-slate-200 lg:sticky lg:top-4">
        <CustomerPicker customer={customer} onChange={setCustomer} />

        <ul className="divide-y divide-slate-100">
          {cart.length === 0 && <li className="py-6 text-center text-sm text-slate-400">Cart is empty</li>}
          {cart.map(({ product, qty }) => (
            <li key={product.id} className="flex items-center gap-2 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{product.name}</p>
                <p className="text-xs text-slate-500">{rupiah(product.price)}</p>
              </div>
              <div className="flex items-center gap-1">
                <QtyButton label="−" onClick={() => setQty(product.id, qty - 1)} />
                <span className="w-6 text-center text-sm tabular-nums">{qty}</span>
                <QtyButton label="+" onClick={() => setQty(product.id, qty + 1)} />
              </div>
              <span className="w-24 text-right text-sm tabular-nums">{rupiah(qty * product.price)}</span>
            </li>
          ))}
        </ul>

        <dl className="space-y-1 border-t border-slate-200 pt-3 text-sm">
          <Row label="Subtotal" value={rupiah(subtotal)} />
          {discount > 0 && <Row label={`${customer?.group} discount (${customer?.discount_rate}%)`} value={`−${rupiah(discount)}`} />}
          <Row label="Total" value={rupiah(total)} strong />
        </dl>

        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-1">
            {(["cash", "card", "qris"] as Method[]).map((m) => (
              <button
                key={m}
                onClick={() => setMethod(m)}
                className={`rounded-md py-1.5 text-sm uppercase ${
                  method === m ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          {method === "cash" && (
            <>
              <input
                inputMode="numeric"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-right tabular-nums"
                placeholder="Cash received"
                value={tendered}
                onChange={(e) => setTendered(e.target.value.replace(/\D/g, ""))}
              />
              <div className="flex flex-wrap gap-1">
                {[total, 50_000, 100_000, 500_000, 1_000_000].filter((v, i, a) => v > 0 && a.indexOf(v) === i).map((v) => (
                  <button key={v} onClick={() => setTendered(String(v))} className="rounded bg-slate-100 px-2 py-1 text-xs">
                    {v === total ? "Exact" : rupiah(v)}
                  </button>
                ))}
              </div>
              {paid >= total && total > 0 && <Row label="Change" value={rupiah(change)} />}
            </>
          )}
        </div>

        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

        <button
          disabled={busy || cart.length === 0 || paid < total}
          onClick={pay}
          className="w-full rounded-lg bg-emerald-600 py-3 font-semibold text-white disabled:opacity-40"
        >
          {busy ? "Saving…" : `Pay ${rupiah(total)}`}
        </button>
      </aside>

      {receipt && <Receipt order={receipt} onClose={() => setReceipt(null)} />}
    </div>
  );
}

function CustomerPicker({ customer, onChange }: { customer: Customer | null; onChange: (c: Customer | null) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Customer[]>([]);

  const searching = q.trim().length >= 2;
  const shown = searching ? results : [];

  useEffect(() => {
    if (!searching) return;
    const timer = setTimeout(() => {
      api<Customer[]>(`/api/customers?q=${encodeURIComponent(q.trim())}&limit=8`).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, searching]);

  if (customer) {
    return (
      <div className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
        <div>
          <p className="font-medium">{customer.name}</p>
          <p className="text-xs text-slate-500">
            {customer.code} · {customer.group ?? "No group"}
          </p>
        </div>
        <button onClick={() => onChange(null)} className="text-xs text-slate-500 hover:text-slate-900">
          Remove
        </button>
      </div>
    );
  }
  return (
    <div className="relative">
      <input
        className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        placeholder="Customer (name, phone, code), optional"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {shown.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md bg-white shadow-lg ring-1 ring-slate-200">
          {shown.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => {
                  onChange(c);
                  setQ("");
                }}
                className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                {c.name} <span className="text-xs text-slate-500">· {c.phone} · {c.group}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Receipt({ order, onClose }: { order: Order; onClose: () => void }) {
  const [current, setCurrent] = useState(order);

  // The ERP push runs after the sale is saved; poll briefly to show its outcome.
  useEffect(() => {
    if (current.push_status !== "pending") return;
    const timer = setTimeout(() => api<Order>(`/api/orders/${order.id}`).then(setCurrent).catch(() => {}), 1000);
    return () => clearTimeout(timer);
  }, [current, order.id]);

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="w-full max-w-sm space-y-3 rounded-xl bg-white p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-slate-500">Paid</p>
            <p className="font-mono text-sm font-semibold">{current.number}</p>
          </div>
          <StatusBadge status={current.push_status} />
        </div>
        <ul className="space-y-1 text-sm">
          {current.lines?.map((l) => (
            <li key={l.product_id} className="flex justify-between gap-2">
              <span className="truncate">
                {l.qty} × {l.name}
              </span>
              <span className="tabular-nums">{rupiah(l.line_total)}</span>
            </li>
          ))}
        </ul>
        <dl className="space-y-1 border-t border-slate-200 pt-2 text-sm">
          {current.discount > 0 && <Row label="Discount" value={`−${rupiah(current.discount)}`} />}
          <Row label="Total" value={rupiah(current.total)} strong />
          <Row label="Paid" value={rupiah(current.paid)} />
          <Row label="Change" value={rupiah(current.change)} />
        </dl>
        <p className="text-xs text-slate-500">
          {current.push_status === "sent"
            ? `Received by the ERP as ${current.erp_number}.`
            : current.push_status === "pending"
              ? current.push_attempts > 0
                ? "ERP unavailable: queued, will retry automatically."
                : "Sending to the ERP…"
              : `ERP rejected it: ${current.last_push_error}`}
        </p>
        <button onClick={onClose} className="w-full rounded-lg bg-slate-900 py-2 text-sm font-medium text-white">
          New sale
        </button>
      </div>
    </div>
  );
}

function QtyButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="h-7 w-7 rounded-md bg-slate-100 text-sm hover:bg-slate-200">
      {label}
    </button>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? "text-base font-semibold" : "text-slate-600"}`}>
      <dt>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
