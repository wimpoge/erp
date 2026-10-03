"use client";

import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, get, post, put } from "@/lib/api";
import { money } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Category, ProductDetail } from "@/lib/types";

const blank = {
  sku: "", name: "", description: "", category_id: "", brand: "", barcode: "", unit: "pcs",
  sale_price: 0, avg_cost: 0, reorder_point: 0, active: true,
};

export function ProductSheet({
  open,
  onOpenChange,
  product,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  product?: ProductDetail | null;
  onSaved?: (p: ProductDetail) => void;
}) {
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => get<Category[]>("/api/categories"),
    enabled: open,
  });
  const [form, setForm] = useState(blank);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<{ open: boolean; id?: number }>({ open: false });
  if (open !== last.open || product?.id !== last.id) {
    setLast({ open, id: product?.id });
    if (open) {
      setError(null);
      setForm(
        product
          ? {
              sku: product.sku, name: product.name, description: product.description ?? "",
              category_id: product.category ? String(product.category.id) : "", brand: product.brand ?? "",
              barcode: product.barcode ?? "", unit: product.unit, sale_price: product.sale_price,
              avg_cost: product.avg_cost, reorder_point: product.reorder_point, active: product.active,
            }
          : blank,
      );
    }
  }

  const save = useAction(() => {
    const body = {
      ...form,
      description: form.description || null,
      brand: form.brand || null,
      barcode: form.barcode || null,
      category_id: form.category_id ? Number(form.category_id) : null,
      avg_cost: product ? undefined : form.avg_cost,
    };
    return product ? put<ProductDetail>(`/api/products/${product.id}`, body) : post<ProductDetail>("/api/products", body);
  }, (p) => `${p.sku} saved.`);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const p = await save.mutateAsync();
      onOpenChange(false);
      onSaved?.(p);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const num = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: Math.max(0, Number(e.target.value)) });
  const categoryItems = [{ value: "", label: "Uncategorised" }, ...(categories ?? []).map((c) => ({ value: String(c.id), label: c.name }))];
  const margin = form.sale_price ? Math.round(((form.sale_price - form.avg_cost) / form.sale_price) * 100) : 0;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="flex h-full flex-col">
          <SheetHeader>
            <SheetTitle>{product ? `Edit ${product.sku}` : "New product"}</SheetTitle>
            <SheetDescription>Prices exclude VAT. Stock is added by receiving a purchase order or a stock count.</SheetDescription>
          </SheetHeader>
          <FieldGroup className="flex-1 px-4">
            <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
              <Field>
                <FieldLabel htmlFor="sku">SKU</FieldLabel>
                <Input id="sku" required value={form.sku} onChange={set("sku")} className="font-mono uppercase" />
              </Field>
              <Field>
                <FieldLabel htmlFor="name">Name</FieldLabel>
                <Input id="name" required value={form.name} onChange={set("name")} />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel>Category</FieldLabel>
                <Select items={categoryItems} value={form.category_id} onValueChange={(v) => setForm({ ...form, category_id: String(v ?? "") })}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {categoryItems.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="brand">Brand</FieldLabel>
                <Input id="brand" value={form.brand} onChange={set("brand")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="barcode">Barcode</FieldLabel>
                <Input id="barcode" value={form.barcode} onChange={set("barcode")} className="font-mono" />
              </Field>
              <Field>
                <FieldLabel htmlFor="unit">Unit</FieldLabel>
                <Input id="unit" value={form.unit} onChange={set("unit")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="price">Sale price (Rp)</FieldLabel>
                <Input id="price" type="number" min={0} step={1000} value={form.sale_price} onChange={num("sale_price")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="cost">Average cost (Rp)</FieldLabel>
                <Input id="cost" type="number" min={0} step={1000} value={form.avg_cost} onChange={num("avg_cost")} disabled={!!product} />
                <FieldDescription>
                  {product ? "Updated automatically on every goods receipt." : "Starting cost, before the first receipt."}
                </FieldDescription>
              </Field>
            </div>
            {form.sale_price > 0 && (
              <p className={`-mt-2 text-sm ${margin < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                Margin {margin}% ({money(form.sale_price - form.avg_cost)} per unit)
              </p>
            )}
            <Field>
              <FieldLabel htmlFor="reorder">Reorder point</FieldLabel>
              <Input id="reorder" type="number" min={0} value={form.reorder_point} onChange={num("reorder_point")} />
              <FieldDescription>Company-wide minimum. At or below it the product shows as low stock.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="desc">Description</FieldLabel>
              <Textarea id="desc" rows={3} value={form.description} onChange={set("description")} />
            </Field>
            {product && (
              <Field orientation="horizontal">
                <input id="active" type="checkbox" className="size-4 accent-primary" checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                <FieldLabel htmlFor="active">Active (can be ordered and sold)</FieldLabel>
              </Field>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </FieldGroup>
          <SheetFooter>
            <Button type="submit" disabled={save.isPending}>{save.isPending && <Spinner />} Save</Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
