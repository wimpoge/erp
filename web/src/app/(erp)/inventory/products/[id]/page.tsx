"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ActivityTimeline } from "@/components/erp/activity";
import { Details, PageHeader, StatCard, StatusBadge } from "@/components/erp/common";
import { moveColumns } from "@/components/erp/moves-table";
import { ProductSheet } from "@/components/erp/product-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { money, qty } from "@/lib/format";
import type { ProductDetail } from "@/lib/types";

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const { data: p } = useQuery({ queryKey: ["/api/products", id], queryFn: () => get<ProductDetail>(`/api/products/${id}`) });
  if (!p) return <Skeleton className="h-[600px]" />;

  const margin = p.sale_price ? ((p.sale_price - p.avg_cost) / p.sale_price) * 100 : 0;
  const cols = [moveColumns.at, moveColumns.kind, moveColumns.warehouse, moveColumns.ref, moveColumns.qty, moveColumns.user];

  return (
    <>
      <PageHeader
        title={p.name}
        badge={
          <>
            {p.low_stock && <Badge variant="destructive">Low stock</Badge>}
            {!p.active && <StatusBadge status="inactive" />}
          </>
        }
        description={
          <span className="font-mono">
            {p.sku}
            {p.barcode && ` · ${p.barcode}`}
          </span>
        }
        actions={
          can("catalog.write") && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Edit
            </Button>
          )
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Sale price" value={money(p.sale_price)} hint={`${margin.toFixed(1)}% margin at current cost`} />
        <StatCard label="Average cost" value={money(p.avg_cost)} hint="Moving average of receipts" />
        <StatCard
          label="Available to sell"
          value={qty(p.available)}
          hint={`${qty(p.on_hand)} on hand · ${qty(p.reserved)} reserved`}
          tone={p.low_stock ? "danger" : undefined}
        />
        <StatCard label="Stock value" value={money(p.stock_value)} hint={p.incoming ? `+${qty(p.incoming)} incoming from suppliers` : "Nothing on order"} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <CardContent>
              <Details
                items={[
                  { label: "Category", value: p.category?.name },
                  { label: "Brand", value: p.brand },
                  { label: "Unit", value: p.unit },
                  { label: "Reorder point", value: qty(p.reorder_point) },
                  ...(p.description ? [{ label: "Description", value: p.description }] : []),
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Stock by warehouse</CardTitle>
              <CardDescription>Reserved = promised on confirmed sales orders. Incoming = on open purchase orders.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Warehouse</TableHead>
                    <TableHead className="text-right">On hand</TableHead>
                    <TableHead className="text-right">Reserved</TableHead>
                    <TableHead className="text-right">Available</TableHead>
                    <TableHead className="text-right">Incoming</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {p.warehouses.map((w) => (
                    <TableRow key={w.warehouse.id}>
                      <TableCell className="font-medium">{w.warehouse.name}</TableCell>
                      <TableCell className="text-right tabular-nums">{qty(w.on_hand)}</TableCell>
                      <TableCell className="text-right tabular-nums">{w.reserved ? qty(w.reserved) : "—"}</TableCell>
                      <TableCell className={`text-right tabular-nums ${w.available < 0 ? "text-destructive" : ""}`}>{qty(w.available)}</TableCell>
                      <TableCell className="text-right tabular-nums">{w.incoming ? `+${qty(w.incoming)}` : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell>Total</TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.on_hand)}</TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.reserved)}</TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.available)}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.incoming ? `+${qty(p.incoming)}` : "—"}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent movements</CardTitle>
              <CardDescription>Every change to this product&apos;s stock, newest first</CardDescription>
              <CardAction>
                <Button variant="ghost" size="sm" render={<Link href={`/inventory/moves?product_id=${p.id}`} />} nativeButton={false}>
                  All movements →
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              {p.recent_moves.length === 0 ? (
                <p className="text-sm text-muted-foreground">No stock movements yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      {cols.map((c) => (
                        <TableHead key={c.key} className={"align" in c && c.align === "right" ? "text-right" : undefined}>{c.header}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {p.recent_moves.map((m) => (
                      <TableRow key={m.id}>
                        {cols.map((c) => (
                          <TableCell key={c.key} className={"align" in c && c.align === "right" ? "text-right" : undefined}>{c.cell(m)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
        <ActivityTimeline items={p.activity} />
      </div>
      <ProductSheet open={editing} onOpenChange={setEditing} product={p} />
    </>
  );
}
