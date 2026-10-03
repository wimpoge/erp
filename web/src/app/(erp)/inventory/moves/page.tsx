"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { PageHeader } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { MOVE_KINDS, moveColumns } from "@/components/erp/moves-table";
import { Badge } from "@/components/ui/badge";
import { get } from "@/lib/api";
import { useWarehouses } from "@/lib/hooks";
import type { ProductDetail, StockMove } from "@/lib/types";

export default function MovesPage() {
  return (
    <Suspense>
      <Moves />
    </Suspense>
  );
}

function Moves() {
  const router = useRouter();
  const productId = useSearchParams().get("product_id");
  const { data: warehouses } = useWarehouses();
  const { data: product } = useQuery({
    queryKey: ["/api/products", productId],
    queryFn: () => get<ProductDetail>(`/api/products/${productId}`),
    enabled: !!productId,
  });

  return (
    <>
      <PageHeader
        title="Stock movements"
        description="The inventory ledger: every unit in or out, with its cost and the document that caused it."
        badge={
          product && (
            <Badge variant="secondary" className="gap-1">
              {product.sku}
              <button aria-label="Show all products" onClick={() => router.replace("/inventory/moves")}>
                <X className="size-3" />
              </button>
            </Badge>
          )
        }
      />
      <DataTable<StockMove>
        endpoint="/api/stock-moves"
        params={productId ? { product_id: productId } : {}}
        searchPlaceholder="Product or document number…"
        filters={[
          { key: "warehouse_id", label: "Warehouses", options: (warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name })) },
          { key: "kind", label: "Types", options: Object.entries(MOVE_KINDS).map(([value, label]) => ({ value, label })) },
        ]}
        columns={[
          moveColumns.at,
          { key: "product", header: "Product", cell: (m) => m.product?.name },
          moveColumns.kind,
          moveColumns.warehouse,
          moveColumns.ref,
          moveColumns.qty,
          moveColumns.cost,
          moveColumns.user,
        ]}
      />
    </>
  );
}
