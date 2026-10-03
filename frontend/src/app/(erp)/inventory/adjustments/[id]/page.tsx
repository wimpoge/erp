"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ActivityTimeline } from "@/components/erp/activity";
import { ConfirmButton, Details, PageHeader, StatusBadge, Totals } from "@/components/erp/common";
import { MoveQty } from "@/components/erp/moves-table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, money, qty } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Adjustment } from "@/lib/types";

export default function AdjustmentPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const { data: a } = useQuery({ queryKey: ["/api/adjustments", id], queryFn: () => get<Adjustment>(`/api/adjustments/${id}`) });
  const validate = useAction(() => post(`/api/adjustments/${id}/validate`), "Count applied; stock corrected.");
  const cancel = useAction(() => post(`/api/adjustments/${id}/cancel`), "Stock count cancelled.");
  if (!a) return <Skeleton className="h-96" />;

  const value = (a.lines ?? []).reduce((s, l) => s + l.value, 0);

  return (
    <>
      <PageHeader
        title={<span className="font-mono">{a.number}</span>}
        badge={<StatusBadge status={a.status} />}
        description={`${a.warehouse.name} · ${a.reason}`}
        actions={
          a.status === "draft" &&
          can("inventory.write") && (
            <>
              <ConfirmButton variant="ghost" title={`Cancel ${a.number}?`} description="Stock stays as it is."
                confirmLabel="Cancel count" destructive onConfirm={() => cancel.mutateAsync()}>
                Cancel
              </ConfirmButton>
              <ConfirmButton title="Apply this count?"
                description={`Stock at ${a.warehouse.name} is set to the counted quantities. The differences (${money(value)} at average cost) are booked as adjustments.`}
                confirmLabel="Apply count" onConfirm={() => validate.mutateAsync()}>
                Apply count
              </ConfirmButton>
            </>
          )
        }
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <CardContent>
              <Details items={[
                { label: "Warehouse", value: a.warehouse.name },
                { label: "Date", value: dateLabel(a.adjustment_date) },
                { label: "Reason", value: a.reason },
                { label: "Counted by", value: a.created_by?.name },
              ]} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Counted products</CardTitle>
              <CardDescription>
                {a.status === "draft" ? "System quantities are live until the count is applied." : "System quantities as they were when the count was applied."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">System</TableHead>
                    <TableHead className="text-right">Counted</TableHead>
                    <TableHead className="text-right">Difference</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {a.lines?.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>
                        <Link href={`/inventory/products/${l.product.id}`} className="font-medium hover:underline">{l.product.name}</Link>
                        <p className="text-xs text-muted-foreground">{l.product.sku}</p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{qty(l.system_qty)}</TableCell>
                      <TableCell className="text-right tabular-nums">{qty(l.counted_qty)}</TableCell>
                      <TableCell className="text-right">{l.difference ? <MoveQty value={l.difference} /> : "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">{l.value ? money(l.value) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Totals rows={[{ label: "Net value of differences", value: money(value), strong: true }]} />
            </CardContent>
          </Card>
        </div>
        <ActivityTimeline items={a.activity ?? []} />
      </div>
    </>
  );
}
