"use client";

import { Minus, PackageSearch, Plus, ScanBarcode, ShoppingCart, Trash2, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PrintableReceipt from "@/components/receipt";
import { useToast } from "@/components/toast";
import { Badge, Button, Dialog, EmptyState, Kbd, Spinner } from "@/components/ui";
import { api, ApiError, Customer, errorMessage, Order, Product, rupiah } from "@/lib/api";
import { useSession } from "@/lib/session";
import { CheckoutDialog, Method, SaleDoneDialog } from "./checkout";
import { CustomerPicker } from "./customer-picker";

type CartLine = { product: Product; qty: number };

export default function TillPage() {
  const { location, register } = useSession();
  const toast = useToast();
  const searchRef = useRef<HTMLInputElement>(null);

  const [products, setProducts] = useState<Product[] | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [pickingCustomer, setPickingCustomer] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [cartOpen, setCartOpen] = useState(false); // phones and small tablets
  const [confirmClear, setConfirmClear] = useState(false);
  const [done, setDone] = useState<Order | null>(null);

  const loadProducts = useCallback(() => {
    if (!location) return;
    api<Product[]>(`/api/products?location_id=${location.id}&limit=1000`)
      .then(setProducts)
      .catch((e) => toast(errorMessage(e), "error"));
  }, [location, toast]);

  useEffect(loadProducts, [loadProducts]);

  const categories = useMemo(() => [...new Set((products ?? []).map((p) => p.category))].sort(), [products]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (products ?? []).filter(
      (p) =>
        (!category || p.category === category) &&
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || p.brand.toLowerCase().includes(q) || p.barcode === q),
    );
  }, [products, query, category]);

  const qtyInCart = (id: number) => cart.find((l) => l.product.id === id)?.qty ?? 0;
  const items = cart.reduce((n, l) => n + l.qty, 0);
  const subtotal = cart.reduce((sum, l) => sum + l.qty * l.product.price, 0);
  const discount = Math.floor((subtotal * (customer?.discount_rate ?? 0)) / 100);
  const total = subtotal - discount;

  const add = useCallback(
    (product: Product) => {
      const inCart = cart.find((l) => l.product.id === product.id)?.qty ?? 0;
      if (inCart >= product.on_hand) {
        toast(product.on_hand === 0 ? `${product.name} is sold out.` : `Only ${product.on_hand} × ${product.name} in stock.`, "error");
        return;
      }
      setCart((lines) =>
        lines.some((l) => l.product.id === product.id)
          ? lines.map((l) => (l.product.id === product.id ? { ...l, qty: l.qty + 1 } : l))
          : [...lines, { product, qty: 1 }],
      );
    },
    [cart, toast],
  );

  function setQty(productId: number, qty: number) {
    setCart((lines) =>
      lines
        .map((l) => (l.product.id === productId ? { ...l, qty: Math.max(0, Math.min(qty, l.product.on_hand)) } : l))
        .filter((l) => l.qty > 0),
    );
  }

  function clearSale() {
    setCart([]);
    setCustomer(null);
    setConfirmClear(false);
    setCartOpen(false);
  }

  function onSearchKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") setQuery("");
    if (e.key !== "Enter") return;
    // Barcode scanners type the code and press Enter.
    const code = query.trim().toLowerCase();
    const exact = products?.find((p) => p.barcode === code || p.sku.toLowerCase() === code);
    const pick = exact ?? (visible.length === 1 ? visible[0] : null);
    if (pick) {
      add(pick);
      setQuery("");
    } else if (code && visible.length === 0) {
      toast(`No product matches “${query.trim()}”.`, "error");
    }
  }

  // Keyboard shortcuts: F2 or / to search, F9 to pay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if (checkingOut || done || pickingCustomer) return;
      if (e.key === "F2" || (e.key === "/" && !typing)) {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "F9" && cart.length > 0) {
        e.preventDefault();
        setCheckingOut(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cart.length, checkingOut, done, pickingCustomer]);

  async function completeSale(method: Method, amount: number) {
    if (!location) return;
    try {
      const order = await api<Order>("/api/orders", {
        method: "POST",
        json: {
          location_id: location.id,
          register_id: register?.id ?? null,
          customer_id: customer?.id ?? null,
          lines: cart.map((l) => ({ product_id: l.product.id, qty: l.qty })),
          payments: [{ method, amount }],
        },
      });
      setCheckingOut(false);
      setDone(order);
      clearSale();
      loadProducts();
    } catch (e) {
      toast(errorMessage(e), "error");
      if (e instanceof ApiError && e.status === 409) {
        // Someone else sold it meanwhile: refresh stock so the cart can be fixed.
        setCheckingOut(false);
        loadProducts();
      }
    }
  }

  function newSale() {
    setDone(null);
    setTimeout(() => searchRef.current?.focus(), 0);
  }

  if (!location) {
    return (
      <EmptyState icon={<PackageSearch className="h-12 w-12" />} title="No store available">
        The store list is empty. An admin needs to run the head-office sync in Back office.
      </EmptyState>
    );
  }

  const cartPanel = (
    <CartPanel
      cart={cart}
      customer={customer}
      items={items}
      subtotal={subtotal}
      discount={discount}
      total={total}
      onQty={setQty}
      onPickCustomer={() => setPickingCustomer(true)}
      onRemoveCustomer={() => setCustomer(null)}
      onClear={() => setConfirmClear(true)}
      onCheckout={() => {
        setCartOpen(false);
        setCheckingOut(true);
      }}
    />
  );

  return (
    <>
      <div className="grid min-w-0 lg:h-[calc(100vh-3.5rem)] lg:grid-cols-[1fr_400px] print:hidden">
        {/* Catalogue */}
        <section className="flex min-h-0 min-w-0 flex-col pb-24 lg:pb-0">
          <div className="space-y-3 border-b border-slate-200 bg-white px-4 py-3">
            <div className="relative">
              <ScanBarcode className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchRef}
                autoFocus
                className="h-12 w-full rounded-xl border border-slate-300 bg-slate-50 pl-11 pr-24 text-base outline-none focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-500/20"
                placeholder="Scan a barcode or search products"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onSearchKey}
              />
              <div className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-2 text-slate-400">
                {query ? (
                  <button onClick={() => setQuery("")} aria-label="Clear search" className="rounded p-1 hover:bg-slate-200 hover:text-slate-700">
                    <X className="h-4 w-4" />
                  </button>
                ) : (
                  <span className="hidden text-xs sm:inline">
                    <Kbd>F2</Kbd>
                  </span>
                )}
              </div>
            </div>
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
              {[null, ...categories].map((c) => (
                <button
                  key={c ?? "all"}
                  onClick={() => setCategory(c)}
                  className={`shrink-0 rounded-full px-4 py-1.5 text-sm font-medium transition ${
                    category === c ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  {c ?? "All products"}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {products === null ? (
              <Spinner label="Loading products…" />
            ) : visible.length === 0 ? (
              <EmptyState icon={<PackageSearch className="h-12 w-12" />} title="No products found">
                {query ? (
                  <>
                    Nothing matches “{query}”.{" "}
                    <button className="font-medium text-sky-700 underline" onClick={() => setQuery("")}>
                      Clear search
                    </button>
                  </>
                ) : (
                  "This store has no products yet."
                )}
              </EmptyState>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
                {visible.map((p) => (
                  <ProductCard key={p.id} product={p} inCart={qtyInCart(p.id)} onAdd={() => add(p)} />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Cart: side panel on large screens */}
        <aside className="hidden min-h-0 border-l border-slate-200 bg-white lg:flex lg:flex-col">{cartPanel}</aside>
      </div>

      {/* Cart: bottom bar + sheet on phones and tablets */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white p-3 lg:hidden print:hidden">
        <button
          onClick={() => setCartOpen(true)}
          className="flex h-14 w-full items-center justify-between rounded-xl bg-slate-900 px-4 text-white"
        >
          <span className="flex items-center gap-2">
            <ShoppingCart className="h-5 w-5" />
            {items === 0 ? "Cart is empty" : `${items} item(s)`}
          </span>
          <span className="text-lg font-semibold tabular-nums">{rupiah(total)}</span>
        </button>
      </div>
      <Dialog open={cartOpen} onClose={() => setCartOpen(false)} title="Current sale">
        <div className="-m-5 flex max-h-[75vh] flex-col">{cartPanel}</div>
      </Dialog>

      <CustomerPicker open={pickingCustomer} onClose={() => setPickingCustomer(false)} onPick={setCustomer} />
      <CheckoutDialog
        open={checkingOut}
        onClose={() => setCheckingOut(false)}
        total={total}
        subtotal={subtotal}
        discount={discount}
        items={items}
        customer={customer}
        onComplete={completeSale}
      />
      <SaleDoneDialog order={done} onNewSale={newSale} />
      <Dialog open={confirmClear} onClose={() => setConfirmClear(false)} title="Clear this sale?">
        <p className="mb-5 text-sm text-slate-600">All {items} item(s) and the customer will be removed from the cart.</p>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" onClick={() => setConfirmClear(false)}>
            Keep it
          </Button>
          <Button variant="danger" data-primary onClick={clearSale}>
            Clear sale
          </Button>
        </div>
      </Dialog>
      <PrintableReceipt order={done} />
    </>
  );
}

function ProductCard({ product, inCart, onAdd }: { product: Product; inCart: number; onAdd: () => void }) {
  const left = product.on_hand - inCart;
  const soldOut = product.on_hand === 0;
  return (
    <button
      onClick={onAdd}
      disabled={soldOut}
      className={`relative flex min-h-36 flex-col rounded-xl bg-white p-3 text-left shadow-sm ring-1 transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${
        inCart ? "ring-2 ring-sky-500" : "ring-slate-200 hover:ring-slate-400"
      }`}
    >
      {inCart > 0 && (
        <span className="absolute -right-2 -top-2 flex h-7 min-w-7 items-center justify-center rounded-full bg-sky-500 px-1.5 text-sm font-bold text-white shadow">
          {inCart}
        </span>
      )}
      <span className="text-xs text-slate-500">{product.brand}</span>
      <span className="mt-0.5 line-clamp-2 text-sm font-medium leading-snug">{product.name}</span>
      <span className="mt-auto pt-3 text-base font-bold tabular-nums">{rupiah(product.price)}</span>
      <span className="mt-1">
        {soldOut ? (
          <Badge tone="red">Sold out</Badge>
        ) : left <= 3 ? (
          <Badge tone="amber">{left === 0 ? "All in cart" : `Only ${left} left`}</Badge>
        ) : (
          <span className="text-xs text-slate-500">{left} in stock</span>
        )}
      </span>
    </button>
  );
}

function CartPanel({
  cart,
  customer,
  items,
  subtotal,
  discount,
  total,
  onQty,
  onPickCustomer,
  onRemoveCustomer,
  onClear,
  onCheckout,
}: {
  cart: CartLine[];
  customer: Customer | null;
  items: number;
  subtotal: number;
  discount: number;
  total: number;
  onQty: (productId: number, qty: number) => void;
  onPickCustomer: () => void;
  onRemoveCustomer: () => void;
  onClear: () => void;
  onCheckout: () => void;
}) {
  return (
    <>
      <div className="border-b border-slate-100 p-4">
        {customer ? (
          <div className="flex items-center gap-3 rounded-xl bg-sky-50 p-3">
            <UserRound className="h-5 w-5 shrink-0 text-sky-700" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{customer.name}</p>
              <p className="text-xs text-slate-600">
                {customer.group}
                {customer.discount_rate > 0 && ` · ${customer.discount_rate}% discount`}
              </p>
            </div>
            <button onClick={onRemoveCustomer} className="rounded p-1 text-slate-500 hover:bg-sky-100" aria-label="Remove customer">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onPickCustomer}
            className="flex w-full items-center gap-3 rounded-xl border border-dashed border-slate-300 p-3 text-left text-sm text-slate-600 hover:border-slate-400 hover:bg-slate-50"
          >
            <UserRound className="h-5 w-5 text-slate-400" />
            <span>
              Walk-in customer · <span className="font-medium text-sky-700">add member</span>
            </span>
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4">
        {cart.length === 0 ? (
          <EmptyState icon={<ShoppingCart className="h-10 w-10" />} title="No items yet">
            Scan a barcode or tap a product to add it.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-slate-100">
            {cart.map(({ product, qty }) => (
              <li key={product.id} className="py-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium leading-snug">{product.name}</p>
                  <button
                    onClick={() => onQty(product.id, 0)}
                    className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                    aria-label={`Remove ${product.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <div className="flex items-center rounded-lg ring-1 ring-slate-200">
                    <button onClick={() => onQty(product.id, qty - 1)} className="flex h-9 w-9 items-center justify-center hover:bg-slate-50" aria-label="One less">
                      <Minus className="h-4 w-4" />
                    </button>
                    <span className="w-10 text-center font-semibold tabular-nums">{qty}</span>
                    <button
                      onClick={() => onQty(product.id, qty + 1)}
                      disabled={qty >= product.on_hand}
                      className="flex h-9 w-9 items-center justify-center hover:bg-slate-50 disabled:opacity-30"
                      aria-label="One more"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold tabular-nums">{rupiah(qty * product.price)}</p>
                    {qty > 1 && <p className="text-xs text-slate-500 tabular-nums">{rupiah(product.price)} each</p>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-3 border-t border-slate-200 p-4">
        <div className="space-y-1 text-sm">
          <div className="flex justify-between text-slate-600">
            <span>Subtotal ({items} item{items === 1 ? "" : "s"})</span>
            <span className="tabular-nums">{rupiah(subtotal)}</span>
          </div>
          {discount > 0 && (
            <div className="flex justify-between text-emerald-700">
              <span>Member discount</span>
              <span className="tabular-nums">−{rupiah(discount)}</span>
            </div>
          )}
          <div className="flex items-baseline justify-between pt-1">
            <span className="font-medium">Total</span>
            <span className="text-2xl font-bold tabular-nums">{rupiah(total)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="xl" onClick={onClear} disabled={cart.length === 0} aria-label="Clear sale" title="Clear sale">
            <Trash2 className="h-5 w-5" />
          </Button>
          <Button variant="success" size="xl" className="flex-1" onClick={onCheckout} disabled={cart.length === 0}>
            Pay {rupiah(total)} <Kbd>F9</Kbd>
          </Button>
        </div>
      </div>
    </>
  );
}
