"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { ProductSheet } from "@/components/erp/product-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { get } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { money, qty } from "@/lib/format";
import { useWarehouses } from "@/lib/hooks";
import type { Category, ProductRow } from "@/lib/types";

export default function ProductsPage() {
  const can = useCan();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const { data: categories } = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/api/categories") });
  const { data: warehouses } = useWarehouses();
  const newButton = can("catalog.write") && (
    <Button onClick={() => setCreating(true)}>
      <Plus /> New product
    </Button>
  );

  return (
    <>
      <PageHeader title="Products" description="The catalogue with prices, average cost and stock across warehouses." actions={newButton} />
      <DataTable<ProductRow>
        endpoint="/api/products"
        rowHref={(p) => `/inventory/products/${p.id}`}
        searchPlaceholder="SKU, name, brand or barcode…"
        filters={[
          { key: "category_id", label: "Categories", options: (categories ?? []).map((c) => ({ value: String(c.id), label: c.name })) },
          { key: "warehouse_id", label: "Warehouses", options: (warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name })) },
          { key: "low_stock", label: "Stock", options: [{ value: "true", label: "Low stock only" }] },
          {
            key: "active",
            label: "Products",
            defaultValue: "true",
            options: [{ value: "true", label: "Active" }, { value: "false", label: "Archived" }],
          },
        ]}
        empty={{ title: "No products yet", action: newButton || undefined }}
        columns={[
          { key: "name", header: "Product", sort: "name", cell: (p) => p.name },
          { key: "sku", header: "SKU", sort: "sku", cell: (p) => <span className="font-mono text-xs">{p.sku}</span> },
          { key: "category", header: "Category", hideBelow: "lg", cell: (p) => p.category?.name ?? "—" },
          { key: "price", header: "Price", sort: "price", align: "right", cell: (p) => money(p.sale_price) },
          { key: "cost", header: "Avg. cost", sort: "cost", align: "right", hideBelow: "lg", cell: (p) => money(p.avg_cost) },
          {
            key: "on_hand",
            header: "On hand",
            sort: "on_hand",
            align: "right",
            cell: (p) => (
              <span className="inline-flex items-center gap-2">
                {p.low_stock && <Badge variant="destructive">Low</Badge>}
                {qty(p.on_hand)}
              </span>
            ),
          },
          { key: "available", header: "Available", align: "right", hideBelow: "md", cell: (p) => qty(p.available) },
          { key: "incoming", header: "Incoming", align: "right", hideBelow: "lg", cell: (p) => (p.incoming ? `+${qty(p.incoming)}` : "—") },
          { key: "status", header: "", hideBelow: "md", cell: (p) => (p.active ? null : <StatusBadge status="inactive" />) },
        ]}
      />
      <ProductSheet open={creating} onOpenChange={setCreating} onSaved={(p) => router.push(`/inventory/products/${p.id}`)} />
    </>
  );
}
