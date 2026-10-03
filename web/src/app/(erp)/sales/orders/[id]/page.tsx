"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileText, Pencil, Truck } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ActivityTimeline } from "@/components/erp/activity";
import { ConfirmButton, Details, PageHeader, StatusBadge, Totals } from "@/components/erp/common";
import { FulfilDialog } from "@/components/erp/fulfil-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { get, post } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, dateTimeLabel, money, qty } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { SalesOrderDetail } from "@/lib/types";

export default function SalesOrderPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan();
  const [delivering, setDelivering] = useState(false);
  const { data: o } = useQuery({
    queryKey: ["/api/sales-orders", id],
    queryFn: () => get<SalesOrderDetail>(`/api/sales-orders/${id}`),
  });

  const confirm = useAction(() => post(`/api/sales-orders/${id}/confirm`), "Order confirmed; the products are reserved.");
  const cancel = useAction(() => post(`/api/sales-orders/${id}/cancel`), "Order cancelled.");
  const deliver = useAction(
    ({ lines, date }: { lines: Record<number, number>; date: string }) =>
      post(`/api/sales-orders/${id}/deliver`, { lines, delivery_date: date }),
    "Delivery recorded and stock updated.",
  );
  const invoice = useAction(
    () => post<{ id: number; number: string }>(`/api/sales-orders/${id}/invoice`),
    (r) => `Invoice ${r.number} created.`,
  );

  if (!o) return <Skeleton className="h-[600px]" />;

  const open = o.status === "confirmed" || o.status === "partially_delivered";
  const toInvoice = o.lines.some((l) => l.qty_delivered > l.qty_invoiced);
  const shortage = open && o.lines.some((l) => l.stock && l.stock.on_hand < l.qty - l.qty_delivered);

  return (
    <>
      <PageHeader
        title={<span className="font-mono">{o.number}</span>}
        badge={
          <>
            <StatusBadge status={o.status} />
            {o.status !== "draft" && o.status !== "cancelled" && <StatusBadge status={o.invoice_status} />}
            {o.source === "api" && <Badge variant="secondary">Imported via API</Badge>}
          </>
        }
        description={
          <>
            For <Link className="font-medium text-foreground hover:underline" href={`/sales/customers/${o.customer.id}`}>{o.customer.name}</Link>{" "}
            · {dateLabel(o.order_date)}
          </>
        }
        actions={
          <>
            {o.status === "draft" && can("sales.write") && (
              <Button variant="outline" render={<Link href={`/sales/orders/${o.id}/edit`} />} nativeButton={false}>
                <Pencil /> Edit
              </Button>
            )}
            {(o.status === "draft" || o.status === "confirmed") && can("sales.write") && (
              <ConfirmButton
                variant="ghost"
                title={`Cancel ${o.number}?`}
                description="The order is kept for the record but can no longer be delivered or invoiced. Reserved stock is released."
                confirmLabel="Cancel order"
                destructive
                onConfirm={() => cancel.mutateAsync()}
              >
                Cancel order
              </ConfirmButton>
            )}
            {o.status === "draft" && can("sales.write") && (
              <ConfirmButton
                title={`Confirm ${o.number}?`}
                description={`This reserves the products at ${o.warehouse.name} and checks ${o.customer.name}'s credit limit. The order can't be edited afterwards.`}
                confirmLabel="Confirm order"
                onConfirm={() => confirm.mutateAsync()}
              >
                Confirm order
              </ConfirmButton>
            )}
            {open && can("sales.deliver") && (
              <Button onClick={() => setDelivering(true)}>
                <Truck /> Deliver
              </Button>
            )}
            {toInvoice && can("finance.write") && (
              <ConfirmButton
                variant={open ? "outline" : "default"}
                title="Create invoice"
                description="Invoices everything that has been delivered and not invoiced yet. Payment terms come from the customer."
                confirmLabel="Create invoice"
                onConfirm={async () => {
                  const r = await invoice.mutateAsync();
                  router.push(`/finance/invoices/${r.id}`);
                }}
              >
                <FileText /> Create invoice
              </ConfirmButton>
            )}
          </>
        }
      />

      {shortage && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          Not everything is in stock at {o.warehouse.name}. You can deliver what is there now and the rest later, or
          transfer stock from another warehouse.
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <CardContent>
              <Details
                items={[
                  { label: "Customer", value: <Link className="hover:underline" href={`/sales/customers/${o.customer.id}`}>{o.customer.name}</Link> },
                  { label: "Ship from", value: o.warehouse.name },
                  { label: "Order date", value: dateLabel(o.order_date) },
                  { label: "Customer reference", value: o.customer_ref },
                  { label: "Created by", value: o.created_by?.name ?? "Integration API" },
                  { label: "Created", value: dateTimeLabel(o.created_at) },
                  ...(o.external_id ? [{ label: "External id", value: <span className="font-mono text-xs">{o.external_id}</span> }] : []),
                  ...(o.note ? [{ label: "Note", value: o.note }] : []),
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Products</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Ordered</TableHead>
                      <TableHead className="text-right">Delivered</TableHead>
                      <TableHead className="text-right">Invoiced</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead className="text-right">Disc.</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {o.lines.map((l) => {
                      const remaining = l.qty - l.qty_delivered;
                      const short = open && l.stock && l.stock.on_hand < remaining;
                      return (
                        <TableRow key={l.id}>
                          <TableCell>
                            <Link className="font-medium hover:underline" href={`/inventory/products/${l.product.id}`}>{l.product.name}</Link>
                            <p className="text-xs text-muted-foreground">
                              {l.product.sku}
                              {open && l.stock && remaining > 0 && (
                                <span className={short ? "text-destructive" : ""}> · {qty(l.stock.on_hand)} on hand</span>
                              )}
                            </p>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{qty(l.qty)}</TableCell>
                          <TableCell className="text-right tabular-nums">{qty(l.qty_delivered)}</TableCell>
                          <TableCell className="text-right tabular-nums">{qty(l.qty_invoiced)}</TableCell>
                          <TableCell className="text-right tabular-nums">{money(l.unit_price)}</TableCell>
                          <TableCell className="text-right tabular-nums">{l.discount_pct ? `${l.discount_pct}%` : "—"}</TableCell>
                          <TableCell className="text-right font-medium tabular-nums">{money(l.line_total)}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
              <Totals
                rows={[
                  ...(o.discount ? [{ label: "Before discount", value: money(o.gross) }, { label: "Discount", value: `−${money(o.discount)}` }] : []),
                  { label: "Subtotal", value: money(o.subtotal) },
                  { label: `VAT ${o.tax_rate}%`, value: money(o.tax) },
                  { label: "Total", value: money(o.total), strong: true },
                ]}
              />
            </CardContent>
          </Card>

          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Deliveries</CardTitle>
              </CardHeader>
              <CardContent>
                {o.deliveries.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nothing shipped yet.</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {o.deliveries.map((d) => (
                      <li key={d.id} className="py-2">
                        <div className="flex justify-between gap-2">
                          <span className="font-mono text-xs">{d.number}</span>
                          <span className="text-muted-foreground">{dateLabel(d.delivery_date)}</span>
                        </div>
                        <Tooltip>
                          <TooltipTrigger render={<p className="w-fit text-muted-foreground" />}>
                            {qty(d.units)} unit(s) · {d.created_by?.name}
                          </TooltipTrigger>
                          <TooltipContent>
                            {d.lines.map((l) => (
                              <div key={l.product.id}>{qty(l.qty)} × {l.product.name}</div>
                            ))}
                          </TooltipContent>
                        </Tooltip>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Invoices</CardTitle>
              </CardHeader>
              <CardContent>
                {o.invoices.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Not invoiced yet.</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {o.invoices.map((i) => (
                      <li key={i.id} className="flex items-center justify-between gap-2 py-2">
                        <Link href={`/finance/invoices/${i.id}`} className="font-mono text-xs hover:underline">{i.number}</Link>
                        <span className="flex items-center gap-2">
                          <span className="tabular-nums">{money(i.total)}</span>
                          <StatusBadge status={i.balance === 0 && i.status !== "cancelled" ? "paid" : i.status} />
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
        <ActivityTimeline items={o.activity} />
      </div>

      <FulfilDialog
        open={delivering}
        onOpenChange={setDelivering}
        title={`Deliver ${o.number}`}
        description={`Ship from ${o.warehouse.name}. Quantities are suggested from what's on hand there; change them for a partial delivery.`}
        dateLabel="Delivery date"
        confirmLabel="Record delivery"
        lines={o.lines
          .filter((l) => l.qty > l.qty_delivered)
          .map((l) => ({
            id: l.id,
            product: l.product,
            remaining: l.qty - l.qty_delivered,
            max: l.stock?.on_hand ?? 0,
            note: `${qty(l.stock?.on_hand ?? 0)} on hand`,
          }))}
        onSubmit={(lines, date) => deliver.mutateAsync({ lines, date })}
      />
    </>
  );
}
