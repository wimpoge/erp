"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { money } from "@/lib/format";
import type { ProductRow } from "@/lib/types";
import { EntityCombobox, Option } from "./entity-combobox";

export type Line = {
  key: number;
  product: Option | null;
  qty: number;
  price: number;
  discount: number;
};

/** What the line editor asks for: a price (sales), a cost (purchasing) or only quantities. */
export type LineMode = "sale" | "purchase" | "quantity" | "count";

let nextKey = 1;
export const newLine = (): Line => ({ key: nextKey++, product: null, qty: 1, price: 0, discount: 0 });

export const productOption = (p: ProductRow): Option => ({
  id: p.id,
  label: `${p.sku} · ${p.name}`,
  hint: `${p.available} available · ${money(p.sale_price)}`,
  data: p,
});

export function lineTotal(l: Line, mode: LineMode) {
  if (mode === "quantity" || mode === "count") return 0;
  return Math.round((l.qty * l.price * (100 - (mode === "sale" ? l.discount : 0))) / 100);
}

export function LinesEditor({
  mode,
  lines,
  onChange,
  defaultDiscount = 0,
  warehouseId,
  showErrors,
}: {
  mode: LineMode;
  lines: Line[];
  onChange: (lines: Line[]) => void;
  defaultDiscount?: number;
  warehouseId?: number;
  showErrors?: boolean;
}) {
  const priced = mode === "sale" || mode === "purchase";
  const update = (key: number, change: Partial<Line>) => onChange(lines.map((l) => (l.key === key ? { ...l, ...change } : l)));

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-64">Product</TableHead>
              <TableHead className="w-28 text-right">{mode === "count" ? "Counted" : "Quantity"}</TableHead>
              {priced && <TableHead className="w-40 text-right">{mode === "sale" ? "Unit price" : "Unit cost"}</TableHead>}
              {mode === "sale" && <TableHead className="w-24 text-right">Disc. %</TableHead>}
              {priced && <TableHead className="w-36 text-right">Amount</TableHead>}
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {lines.map((l) => (
              <TableRow key={l.key} className="hover:bg-transparent">
                <TableCell>
                  <EntityCombobox<ProductRow>
                    endpoint="/api/products"
                    params={warehouseId ? { warehouse_id: warehouseId } : undefined}
                    toOption={productOption}
                    value={l.product}
                    invalid={showErrors && !l.product}
                    placeholder="Search SKU or name…"
                    className="w-full"
                    onChange={(o) => {
                      const p = o?.data as ProductRow | undefined;
                      update(l.key, {
                        product: o,
                        price: p ? (mode === "purchase" ? p.avg_cost : p.sale_price) : 0,
                        discount: defaultDiscount,
                      });
                    }}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    type="number"
                    min={mode === "count" ? 0 : 1}
                    className="text-right tabular-nums"
                    value={l.qty}
                    aria-invalid={showErrors && (mode === "count" ? l.qty < 0 : l.qty < 1) ? true : undefined}
                    onChange={(e) => update(l.key, { qty: Math.max(0, Math.floor(Number(e.target.value))) })}
                  />
                </TableCell>
                {priced && (
                  <TableCell>
                    <Input
                      type="number"
                      min={0}
                      step={1000}
                      className="text-right tabular-nums"
                      value={l.price}
                      onChange={(e) => update(l.key, { price: Math.max(0, Math.floor(Number(e.target.value))) })}
                    />
                  </TableCell>
                )}
                {mode === "sale" && (
                  <TableCell>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      className="text-right tabular-nums"
                      value={l.discount}
                      onChange={(e) => update(l.key, { discount: Math.min(100, Math.max(0, Math.floor(Number(e.target.value)))) })}
                    />
                  </TableCell>
                )}
                {priced && <TableCell className="text-right font-medium tabular-nums">{money(lineTotal(l, mode))}</TableCell>}
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Remove line"
                    disabled={lines.length === 1}
                    onClick={() => onChange(lines.filter((x) => x.key !== l.key))}
                  >
                    <Trash2 />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Button variant="outline" size="sm" onClick={() => onChange([...lines, newLine()])}>
        <Plus /> Add line
      </Button>
    </div>
  );
}

export function validLines(lines: Line[], mode: LineMode): boolean {
  return lines.every((l) => l.product && (mode === "count" ? l.qty >= 0 : l.qty >= 1));
}
