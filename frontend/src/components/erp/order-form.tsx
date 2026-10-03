"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, post, put } from "@/lib/api";
import { money, todayIso } from "@/lib/format";
import { useCompany, useWarehouses } from "@/lib/hooks";
import type { Customer, PurchaseOrderDetail, SalesOrderDetail, Supplier } from "@/lib/types";
import { Totals } from "./common";
import { EntityCombobox, Option } from "./entity-combobox";
import { Line, LinesEditor, lineTotal, newLine, validLines } from "./lines-editor";

type Kind = "sales" | "purchase";

const customerOption = (c: Customer): Option => ({
  id: c.id,
  label: c.name,
  hint: [c.code, c.group ? (c.group.discount_pct ? `${c.group.name} −${c.group.discount_pct}%` : c.group.name) : null, c.city].filter(Boolean).join(" · "),
  data: c,
});
const supplierOption = (s: Supplier): Option => ({
  id: s.id,
  label: s.name,
  hint: [s.code, `${s.payment_terms_days} days terms`, s.city].filter(Boolean).join(" · "),
  data: s,
});

export function OrderForm({
  kind,
  order,
}: {
  kind: Kind;
  order?: SalesOrderDetail | PurchaseOrderDetail;
}) {
  const router = useRouter();
  const sales = kind === "sales";
  const { data: warehouses } = useWarehouses();
  const { data: company } = useCompany();
  const so = sales ? (order as SalesOrderDetail | undefined) : undefined;
  const po = !sales ? (order as PurchaseOrderDetail | undefined) : undefined;

  const [partner, setPartner] = useState<Option | null>(
    so ? { id: so.customer.id, label: so.customer.name } : po ? { id: po.supplier.id, label: po.supplier.name } : null,
  );
  const [warehouseId, setWarehouseId] = useState<string>(order ? String(order.warehouse.id) : "");
  const [orderDate, setOrderDate] = useState(order?.order_date ?? todayIso());
  const [expectedDate, setExpectedDate] = useState(po?.expected_date ?? "");
  const [reference, setReference] = useState((so?.customer_ref ?? po?.supplier_ref) ?? "");
  const [note, setNote] = useState(order?.note ?? "");
  const [lines, setLines] = useState<Line[]>(() =>
    order
      ? order.lines.map((l) => ({
          ...newLine(),
          product: { id: l.product.id, label: `${l.product.sku} · ${l.product.name}` },
          qty: l.qty,
          price: "unit_price" in l ? l.unit_price : l.unit_cost,
          discount: "discount_pct" in l ? l.discount_pct : 0,
        }))
      : [newLine()],
  );
  const [showErrors, setShowErrors] = useState(false);
  const [busy, setBusy] = useState<null | "draft" | "confirm">(null);
  const [error, setError] = useState<string | null>(null);

  const mode = sales ? "sale" : "purchase";
  const groupDiscount = sales ? ((partner?.data as Customer | undefined)?.group?.discount_pct ?? 0) : 0;
  const gross = lines.reduce((s, l) => s + l.qty * l.price, 0);
  const subtotal = lines.reduce((s, l) => s + lineTotal(l, mode), 0);
  const taxRate = order?.tax_rate ?? company?.tax_rate ?? 11;
  const tax = Math.round((subtotal * taxRate) / 100);

  const warehouseItems = (warehouses ?? []).map((w) => ({ value: String(w.id), label: `${w.code} · ${w.name}` }));

  async function save(confirm: boolean) {
    setShowErrors(true);
    setError(null);
    if (!partner || !warehouseId || !validLines(lines, mode)) {
      setError("Fill in the highlighted fields: a " + (sales ? "customer" : "supplier") + ", a warehouse and a product on every line.");
      return;
    }
    setBusy(confirm ? "confirm" : "draft");
    const body = {
      [sales ? "customer_id" : "supplier_id"]: partner.id,
      warehouse_id: Number(warehouseId),
      order_date: orderDate,
      ...(sales
        ? { customer_ref: reference || null }
        : { supplier_ref: reference || null, expected_date: expectedDate || null }),
      note: note || null,
      lines: lines.map((l) =>
        sales
          ? { product_id: l.product!.id, qty: l.qty, unit_price: l.price, discount_pct: l.discount }
          : { product_id: l.product!.id, qty: l.qty, unit_cost: l.price },
      ),
    };
    const base = sales ? "/api/sales-orders" : "/api/purchase-orders";
    try {
      const saved = order ? await put<{ id: number; number: string }>(`${base}/${order.id}`, body)
        : await post<{ id: number; number: string }>(base, body);
      if (confirm) await post(`${base}/${saved.id}/confirm`);
      toast.success(`${saved.number} ${confirm ? (sales ? "confirmed" : "sent to the supplier") : "saved as draft"}`);
      router.push(`${sales ? "/sales/orders" : "/purchasing/orders"}/${saved.id}`);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{sales ? "Customer & delivery" : "Supplier & delivery"}</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldGroup className="grid gap-4 md:grid-cols-2">
              <Field data-invalid={showErrors && !partner}>
                <FieldLabel>{sales ? "Customer" : "Supplier"}</FieldLabel>
                {sales ? (
                  <EntityCombobox<Customer>
                    endpoint="/api/customers"
                    toOption={customerOption}
                    value={partner}
                    invalid={showErrors && !partner}
                    placeholder="Search name, code or phone…"
                    onChange={(o) => {
                      setPartner(o);
                      const d = (o?.data as Customer | undefined)?.group?.discount_pct ?? 0;
                      setLines((ls) => ls.map((l) => ({ ...l, discount: d })));
                    }}
                  />
                ) : (
                  <EntityCombobox<Supplier>
                    endpoint="/api/suppliers"
                    toOption={supplierOption}
                    value={partner}
                    invalid={showErrors && !partner}
                    placeholder="Search supplier…"
                    onChange={setPartner}
                  />
                )}
                {sales && partner?.data ? <CustomerCredit customer={partner.data as Customer} /> : null}
              </Field>
              <Field data-invalid={showErrors && !warehouseId}>
                <FieldLabel>{sales ? "Ship from" : "Deliver to"}</FieldLabel>
                <Select items={warehouseItems} value={warehouseId || null} onValueChange={(v) => setWarehouseId(String(v ?? ""))}>
                  <SelectTrigger className="w-full" aria-invalid={showErrors && !warehouseId ? true : undefined}>
                    <SelectValue placeholder="Choose a warehouse" />
                  </SelectTrigger>
                  <SelectContent>
                    {warehouseItems.map((w) => (
                      <SelectItem key={w.value} value={w.value}>
                        {w.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="order-date">Order date</FieldLabel>
                <Input id="order-date" type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
              </Field>
              {!sales && (
                <Field>
                  <FieldLabel htmlFor="expected">Expected delivery</FieldLabel>
                  <Input id="expected" type="date" value={expectedDate} onChange={(e) => setExpectedDate(e.target.value)} />
                </Field>
              )}
              <Field>
                <FieldLabel htmlFor="ref">{sales ? "Customer reference" : "Supplier quote / reference"}</FieldLabel>
                <Input id="ref" placeholder={sales ? "e.g. their PO number" : "e.g. quote number"} value={reference}
                  onChange={(e) => setReference(e.target.value)} />
              </Field>
              <Field className="md:col-span-2">
                <FieldLabel htmlFor="note">Internal note</FieldLabel>
                <Textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Products</CardTitle>
          </CardHeader>
          <CardContent>
            <LinesEditor
              mode={mode}
              lines={lines}
              onChange={setLines}
              defaultDiscount={groupDiscount}
              warehouseId={warehouseId ? Number(warehouseId) : undefined}
              showErrors={showErrors}
            />
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Totals
              rows={[
                ...(sales && gross !== subtotal ? [{ label: "Before discount", value: money(gross) }, { label: "Discount", value: `−${money(gross - subtotal)}` }] : []),
                { label: "Subtotal", value: money(subtotal) },
                { label: `VAT ${taxRate}%`, value: money(tax) },
                { label: "Total", value: money(subtotal + tax), strong: true },
              ]}
            />
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="grid gap-2">
              <Button disabled={busy !== null} onClick={() => save(true)}>
                {busy === "confirm" && <Spinner />} {sales ? "Save and confirm" : "Save and send to supplier"}
              </Button>
              <Button variant="outline" disabled={busy !== null} onClick={() => save(false)}>
                {busy === "draft" && <Spinner />} Save as draft
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => router.back()}>
                Cancel
              </Button>
            </div>
            <FieldDescription>
              {sales
                ? "Confirming checks the customer's credit limit and reserves the products."
                : "Once sent, the order can be received in one or more deliveries."}
            </FieldDescription>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CustomerCredit({ customer }: { customer: Customer }) {
  if (!customer.credit_limit && !customer.balance) return null;
  return (
    <FieldDescription className={customer.overdue ? "text-destructive" : undefined}>
      Owes {money(customer.balance)}
      {customer.overdue ? ` (${money(customer.overdue)} overdue)` : ""}
      {customer.credit_limit ? ` · credit limit ${money(customer.credit_limit)}` : ""}
    </FieldDescription>
  );
}
