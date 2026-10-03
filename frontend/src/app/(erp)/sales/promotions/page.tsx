"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Tag } from "lucide-react";
import { FormEvent, useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { EntityCombobox, type Option } from "@/components/erp/entity-combobox";
import { productOption } from "@/components/erp/lines-editor";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, get, post, put } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, money } from "@/lib/format";
import { useAction, useWarehouses } from "@/lib/hooks";
import type { Category, ProductRow, Promotion, PromotionKind } from "@/lib/types";

const KIND_LABEL: Record<PromotionKind, string> = {
  percent: "Percentage off",
  price: "Special price",
  buy_get: "Buy X get Y free",
  voucher: "Voucher code",
};

/** "10% off", "Rp 900.000", "Buy 2 get 1 free", "PAYDAY: 5% off from Rp 500.000". */
function describe(p: Promotion): string {
  if (p.kind === "percent") return `${p.value}% off`;
  if (p.kind === "price") return `${money(p.value)} each`;
  if (p.kind === "buy_get") return `Buy ${p.buy_qty} get ${p.get_qty} free`;
  return `${p.code}: ${p.value}% off${p.min_spend ? ` from ${money(p.min_spend)}` : ""}`;
}

const appliesTo = (p: Promotion) =>
  p.product ? p.product.name : p.category ? `Category ${p.category.name}` : "Everything";

export default function PromotionsPage() {
  const can = useCan();
  const [editing, setEditing] = useState<Promotion | "new" | null>(null);
  const { data } = useQuery({ queryKey: ["promotions"], queryFn: () => get<Promotion[]>("/api/promotions") });

  return (
    <>
      <PageHeader
        title="Promotions"
        description="Applied by the POS tills. They never stack: each item gets its single best discount."
        actions={
          can("sales.write") && (
            <Button onClick={() => setEditing("new")}>
              <Plus /> New promotion
            </Button>
          )
        }
      />
      {data?.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Tag />
            </EmptyMedia>
            <EmptyTitle>No promotions yet</EmptyTitle>
            <EmptyDescription>Special prices, percentages off, buy X get Y and voucher codes for the tills.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Promotion</TableHead>
                <TableHead>Applies to</TableHead>
                <TableHead className="hidden lg:table-cell">Stores</TableHead>
                <TableHead className="hidden md:table-cell">Dates</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {!data && (
                <TableRow>
                  <TableCell colSpan={6} className="py-10">
                    <Spinner className="mx-auto" />
                  </TableCell>
                </TableRow>
              )}
              {data?.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-xs text-muted-foreground">{describe(p)}</div>
                  </TableCell>
                  <TableCell className="max-w-56 truncate">{appliesTo(p)}</TableCell>
                  <TableCell className="hidden lg:table-cell">{p.warehouse ? p.warehouse.name : "All stores"}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {p.starts_on || p.ends_on ? `${p.starts_on ? dateLabel(p.starts_on) : "Now"} – ${p.ends_on ? dateLabel(p.ends_on) : "no end"}` : "Always"}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={p.status} />
                  </TableCell>
                  <TableCell>
                    {can("sales.write") && (
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>
                        <Pencil />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      <PromotionDialog promotion={editing} onClose={() => setEditing(null)} />
    </>
  );
}

type Form = {
  name: string;
  kind: PromotionKind;
  value: string;
  product: Option | null;
  category_id: string;
  warehouse_id: string;
  buy_qty: string;
  get_qty: string;
  code: string;
  min_spend: string;
  starts_on: string;
  ends_on: string;
  active: boolean;
};

const EMPTY: Form = {
  name: "", kind: "percent", value: "", product: null, category_id: "", warehouse_id: "", buy_qty: "2", get_qty: "1",
  code: "", min_spend: "", starts_on: "", ends_on: "", active: true,
};

function toForm(p: Promotion): Form {
  return {
    name: p.name, kind: p.kind, value: String(p.value || ""),
    product: p.product ? { id: p.product.id, label: `${p.product.sku} · ${p.product.name}` } : null,
    category_id: p.category ? String(p.category.id) : "", warehouse_id: p.warehouse ? String(p.warehouse.id) : "",
    buy_qty: String(p.buy_qty || 2), get_qty: String(p.get_qty || 1), code: p.code ?? "",
    min_spend: p.min_spend ? String(p.min_spend) : "", starts_on: p.starts_on ?? "", ends_on: p.ends_on ?? "", active: p.active,
  };
}

const selectClass = "h-9 w-full rounded-lg border bg-transparent px-2 text-sm dark:bg-input/30";

function PromotionDialog({ promotion, onClose }: { promotion: Promotion | "new" | null; onClose: () => void }) {
  const existing = promotion && promotion !== "new" ? promotion : null;
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<typeof promotion>(null);
  if (promotion !== last) {
    setLast(promotion);
    setError(null);
    setForm(existing ? toForm(existing) : EMPTY);
  }
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/api/categories"), enabled: promotion !== null });
  const warehouses = useWarehouses();

  const save = useAction(() => {
    const n = (v: string) => Number(v.replace(/\D/g, "")) || 0;
    const body = {
      name: form.name, kind: form.kind, value: n(form.value), product_id: form.product?.id ?? null,
      category_id: form.kind === "percent" && form.category_id ? Number(form.category_id) : null,
      warehouse_id: form.warehouse_id ? Number(form.warehouse_id) : null, buy_qty: n(form.buy_qty), get_qty: n(form.get_qty),
      code: form.code || null, min_spend: n(form.min_spend), starts_on: form.starts_on || null, ends_on: form.ends_on || null,
      active: form.active,
    };
    return existing ? put(`/api/promotions/${existing.id}`, body) : post("/api/promotions", body);
  }, "Promotion saved. Tills pick it up at their next sync.");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await save.mutateAsync();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const needsProduct = form.kind === "price" || form.kind === "buy_get";

  return (
    <Dialog open={promotion !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{existing ? `Edit ${existing.name}` : "New promotion"}</DialogTitle>
            <DialogDescription>Prices are before VAT, like every price in the ERP.</DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="p-name">Name</FieldLabel>
                <Input id="p-name" required maxLength={80} value={form.name} onChange={set("name")} placeholder="e.g. Payday weekend" />
              </Field>
              <Field>
                <FieldLabel htmlFor="p-kind">Kind</FieldLabel>
                <select id="p-kind" className={selectClass} value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value as PromotionKind })}>
                  {(Object.keys(KIND_LABEL) as PromotionKind[]).map((k) => (
                    <option key={k} value={k}>{KIND_LABEL[k]}</option>
                  ))}
                </select>
              </Field>
            </div>

            {form.kind !== "voucher" && (
              <Field>
                <FieldLabel>Product{form.kind === "percent" && <span className="font-normal text-muted-foreground"> (optional)</span>}</FieldLabel>
                <EntityCombobox<ProductRow>
                  endpoint="/api/products"
                  toOption={productOption}
                  value={form.product}
                  invalid={needsProduct && !form.product && !!error}
                  placeholder="Search SKU or name…"
                  className="w-full"
                  onChange={(o) => setForm({ ...form, product: o, category_id: o ? "" : form.category_id })}
                />
              </Field>
            )}
            {form.kind === "percent" && !form.product && (
              <Field>
                <FieldLabel htmlFor="p-cat">Category</FieldLabel>
                <select id="p-cat" className={selectClass} value={form.category_id} onChange={set("category_id")}>
                  <option value="">Everything</option>
                  {categories.data?.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </Field>
            )}

            {form.kind === "buy_get" ? (
              <div className="grid grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="p-buy">Buy</FieldLabel>
                  <Input id="p-buy" inputMode="numeric" required value={form.buy_qty} onChange={set("buy_qty")} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="p-get">Get free</FieldLabel>
                  <Input id="p-get" inputMode="numeric" required value={form.get_qty} onChange={set("get_qty")} />
                </Field>
              </div>
            ) : (
              <Field>
                <FieldLabel htmlFor="p-value">{form.kind === "price" ? "Special price (Rp)" : "Discount (%)"}</FieldLabel>
                <Input id="p-value" inputMode="numeric" required value={form.value} onChange={set("value")} className="w-40 tabular-nums" />
              </Field>
            )}

            {form.kind === "voucher" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="p-code">Code</FieldLabel>
                  <Input id="p-code" required maxLength={30} className="font-mono uppercase" value={form.code} onChange={set("code")} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="p-min">Minimum spend (Rp)</FieldLabel>
                  <Input id="p-min" inputMode="numeric" value={form.min_spend} onChange={set("min_spend")} placeholder="0" />
                </Field>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-3">
              <Field>
                <FieldLabel htmlFor="p-store">Stores</FieldLabel>
                <select id="p-store" className={selectClass} value={form.warehouse_id} onChange={set("warehouse_id")}>
                  <option value="">All stores</option>
                  {warehouses.data?.map((w) => (
                    <option key={w.id} value={w.id}>{w.name}</option>
                  ))}
                </select>
              </Field>
              <Field>
                <FieldLabel htmlFor="p-from">From</FieldLabel>
                <Input id="p-from" type="date" value={form.starts_on} onChange={set("starts_on")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="p-to">Until</FieldLabel>
                <Input id="p-to" type="date" value={form.ends_on} onChange={set("ends_on")} />
              </Field>
            </div>
            <FieldDescription>Leave the dates empty to run it until you switch it off.</FieldDescription>
            {existing && (
              <Field orientation="horizontal">
                <input id="p-active" type="checkbox" className="size-4 accent-primary" checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                <FieldLabel htmlFor="p-active">Active</FieldLabel>
              </Field>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>{save.isPending && <Spinner />} Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
