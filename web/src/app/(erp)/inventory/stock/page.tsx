"use client";

import Link from "next/link";
import { PageHeader } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Badge } from "@/components/ui/badge";
import { money, qty } from "@/lib/format";
import { useWarehouses } from "@/lib/hooks";
import type { CodeRef, ProductRef } from "@/lib/types";

type StockRow = {
  id: number;
  product: ProductRef;
  warehouse: CodeRef;
  on_hand: number;
  reserved: number;
  available: number;
  unit_cost: number;
  value: number;
  reorder_point: number;
};

export default function StockPage() {
  const { data: warehouses } = useWarehouses();
  return (
    <>
      <PageHeader title="Stock levels" description="What is on the shelf in each warehouse, what is promised, and what it is worth." />
      <DataTable<StockRow>
        endpoint="/api/stock"
        rowHref={(s) => `/inventory/products/${s.product.id}`}
        searchPlaceholder="SKU or product name…"
        filters={[
          { key: "warehouse_id", label: "Warehouses", options: (warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name })) },
        ]}
        columns={[
          { key: "product", header: "Product", sort: "product", cell: (s) => s.product.name },
          { key: "sku", header: "SKU", hideBelow: "md", cell: (s) => <span className="font-mono text-xs">{s.product.sku}</span> },
          { key: "warehouse", header: "Warehouse", cell: (s) => s.warehouse.name },
          {
            key: "on_hand",
            header: "On hand",
            sort: "on_hand",
            align: "right",
            cell: (s) => (s.on_hand === 0 ? <Badge variant="outline">0</Badge> : qty(s.on_hand)),
          },
          { key: "reserved", header: "Reserved", align: "right", hideBelow: "md", cell: (s) => (s.reserved ? qty(s.reserved) : "—") },
          {
            key: "available",
            header: "Available",
            align: "right",
            cell: (s) => <span className={s.available < 0 ? "text-destructive" : undefined}>{qty(s.available)}</span>,
          },
          { key: "cost", header: "Unit cost", align: "right", hideBelow: "lg", cell: (s) => money(s.unit_cost) },
          { key: "value", header: "Value", sort: "value", align: "right", cell: (s) => money(s.value) },
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Need to move stock between locations? Use a <Link className="underline" href="/inventory/transfers/new">transfer</Link>. Found a
        difference on the shelf? Record a <Link className="underline" href="/inventory/adjustments/new">stock count</Link>.
      </p>
    </>
  );
}
