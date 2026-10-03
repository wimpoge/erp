"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ActivityTimeline } from "@/components/erp/activity";
import { ConfirmButton, Details, PageHeader, StatusBadge } from "@/components/erp/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, qty } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Transfer } from "@/lib/types";

export default function TransferPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const { data: t } = useQuery({ queryKey: ["/api/transfers", id], queryFn: () => get<Transfer>(`/api/transfers/${id}`) });
  const validate = useAction(() => post(`/api/transfers/${id}/validate`), "Stock moved.");
  const cancel = useAction(() => post(`/api/transfers/${id}/cancel`), "Transfer cancelled.");
  if (!t) return <Skeleton className="h-96" />;

  return (
    <>
      <PageHeader
        title={<span className="font-mono">{t.number}</span>}
        badge={<StatusBadge status={t.status} />}
        description={`${t.from_warehouse.name} → ${t.to_warehouse.name}`}
        actions={
          t.status === "draft" &&
          can("inventory.write") && (
            <>
              <ConfirmButton variant="ghost" title={`Cancel ${t.number}?`} description="Nothing has moved yet; the draft is kept for the record."
                confirmLabel="Cancel transfer" destructive onConfirm={() => cancel.mutateAsync()}>
                Cancel
              </ConfirmButton>
              <ConfirmButton title={`Move the stock now?`}
                description={`${qty(t.units)} unit(s) leave ${t.from_warehouse.name} and arrive at ${t.to_warehouse.name}. If something is not in stock, nothing moves.`}
                confirmLabel="Move stock" onConfirm={() => validate.mutateAsync()}>
                Validate transfer
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
                { label: "From", value: t.from_warehouse.name },
                { label: "To", value: t.to_warehouse.name },
                { label: "Date", value: dateLabel(t.transfer_date) },
                { label: "Created by", value: t.created_by?.name },
                ...(t.note ? [{ label: "Note", value: t.note }] : []),
              ]} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Products</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {t.lines?.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>
                        <Link href={`/inventory/products/${l.product.id}`} className="font-medium hover:underline">{l.product.name}</Link>
                        <p className="text-xs text-muted-foreground">{l.product.sku}</p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{qty(l.qty)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
        <ActivityTimeline items={t.activity ?? []} />
      </div>
    </>
  );
}
