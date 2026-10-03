"use client";

import { useQuery } from "@tanstack/react-query";
import { PackageCheck, Pencil, ReceiptText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ActivityTimeline } from "@/components/erp/activity";
import { ConfirmButton, Details, PageHeader, StatusBadge, Totals } from "@/components/erp/common";
import { FulfilDialog } from "@/components/erp/fulfil-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, dateTimeLabel, money, qty, todayIso } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { PurchaseOrderDetail } from "@/lib/types";

export default function PurchaseOrderPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const [receiving, setReceiving] = useState(false);
  const [billing, setBilling] = useState(false);
  const { data: o } = useQuery({
    queryKey: ["/api/purchase-orders", id],
    queryFn: () => get<PurchaseOrderDetail>(`/api/purchase-orders/${id}`),
  });

  const confirm = useAction(() => post(`/api/purchase-orders/${id}/confirm`), "Order sent to the supplier.");
  const cancel = useAction(() => post(`/api/purchase-orders/${id}/cancel`), "Order cancelled.");
  const receive = useAction(
    ({ lines, date }: { lines: Record<number, number>; date: string }) =>
      post(`/api/purchase-orders/${id}/receive`, { lines, receipt_date: date }),
    "Goods received; stock and average cost updated.",
  );

  if (!o) return <Skeleton className="h-[600px]" />;

  const open = o.status === "confirmed" || o.status === "partially_received";
  const toBill = o.lines.some((l) => l.qty_received > l.qty_billed);

  return (
    <>
      <PageHeader
        title={<span className="font-mono">{o.number}</span>}
        badge={
          <>
            <StatusBadge status={o.status} />
            {o.status !== "draft" && o.status !== "cancelled" && <StatusBadge status={o.billing_status} />}
          </>
        }
        description={
          <>
            From <Link className="font-medium text-foreground hover:underline" href={`/purchasing/suppliers/${o.supplier.id}`}>{o.supplier.name}</Link>{" "}
            · {dateLabel(o.order_date)}
          </>
        }
        actions={
          <>
            {o.status === "draft" && can("purchasing.write") && (
              <Button variant="outline" render={<Link href={`/purchasing/orders/${o.id}/edit`} />} nativeButton={false}>
                <Pencil /> Edit
              </Button>
            )}
            {(o.status === "draft" || o.status === "confirmed") && can("purchasing.write") && (
              <ConfirmButton
                variant="ghost"
                title={`Cancel ${o.number}?`}
                description="Tell the supplier as well. The order is kept for the record."
                confirmLabel="Cancel order"
                destructive
                onConfirm={() => cancel.mutateAsync()}
              >
                Cancel order
              </ConfirmButton>
            )}
            {o.status === "draft" && can("purchasing.write") && (
              <ConfirmButton
                title={`Send ${o.number}?`}
                description={`Marks the order as sent to ${o.supplier.name}. The quantities show as incoming stock at ${o.warehouse.name}.`}
                confirmLabel="Mark as sent"
                onConfirm={() => confirm.mutateAsync()}
              >
                Send to supplier
              </ConfirmButton>
            )}
            {open && can("purchasing.receive") && (
              <Button onClick={() => setReceiving(true)}>
                <PackageCheck /> Receive goods
              </Button>
            )}
            {toBill && can("finance.write") && (
              <Button variant={open ? "outline" : "default"} onClick={() => setBilling(true)}>
                <ReceiptText /> Record bill
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <CardContent>
              <Details
                items={[
                  { label: "Supplier", value: <Link className="hover:underline" href={`/purchasing/suppliers/${o.supplier.id}`}>{o.supplier.name}</Link> },
                  { label: "Deliver to", value: o.warehouse.name },
                  { label: "Order date", value: dateLabel(o.order_date) },
                  { label: "Expected", value: dateLabel(o.expected_date) },
                  { label: "Supplier reference", value: o.supplier_ref },
                  { label: "Created by", value: o.created_by?.name },
                  { label: "Created", value: dateTimeLabel(o.created_at) },
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
                      <TableHead className="text-right">Received</TableHead>
                      <TableHead className="text-right">Billed</TableHead>
                      <TableHead className="text-right">Unit cost</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {o.lines.map((l) => (
                      <TableRow key={l.id}>
                        <TableCell>
                          <Link className="font-medium hover:underline" href={`/inventory/products/${l.product.id}`}>{l.product.name}</Link>
                          <p className="text-xs text-muted-foreground">{l.product.sku}</p>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{qty(l.qty)}</TableCell>
                        <TableCell className="text-right tabular-nums">{qty(l.qty_received)}</TableCell>
                        <TableCell className="text-right tabular-nums">{qty(l.qty_billed)}</TableCell>
                        <TableCell className="text-right tabular-nums">{money(l.unit_cost)}</TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{money(l.line_total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <Totals
                rows={[
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
                <CardTitle>Goods receipts</CardTitle>
              </CardHeader>
              <CardContent>
                {o.receipts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nothing received yet.</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {o.receipts.map((r) => (
                      <li key={r.id} className="py-2">
                        <div className="flex justify-between gap-2">
                          <span className="font-mono text-xs">{r.number}</span>
                          <span className="text-muted-foreground">{dateLabel(r.receipt_date)}</span>
                        </div>
                        <p className="text-muted-foreground">
                          {qty(r.units)} unit(s) · {r.created_by?.name}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Supplier bills</CardTitle>
              </CardHeader>
              <CardContent>
                {o.bills.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No bill recorded yet.</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {o.bills.map((b) => (
                      <li key={b.id} className="flex items-center justify-between gap-2 py-2">
                        <Link href={`/finance/bills/${b.id}`} className="font-mono text-xs hover:underline">{b.number}</Link>
                        <span className="flex items-center gap-2">
                          <span className="tabular-nums">{money(b.total)}</span>
                          <StatusBadge status={b.status} />
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
        open={receiving}
        onOpenChange={setReceiving}
        title={`Receive ${o.number}`}
        description={`Count what arrived at ${o.warehouse.name}. If the supplier shipped short, enter what you got; the rest stays open.`}
        dateLabel="Received on"
        confirmLabel="Book into stock"
        lines={o.lines
          .filter((l) => l.qty > l.qty_received)
          .map((l) => ({ id: l.id, product: l.product, remaining: l.qty - l.qty_received, max: l.qty - l.qty_received }))}
        onSubmit={(lines, date) => receive.mutateAsync({ lines, date })}
      />
      <BillDialog open={billing} onOpenChange={setBilling} order={o} />
    </>
  );
}

function BillDialog({ open, onOpenChange, order }: { open: boolean; onOpenChange: (o: boolean) => void; order: PurchaseOrderDetail }) {
  const router = useRouter();
  const [ref, setRef] = useState("");
  const [date, setDate] = useState(todayIso());
  const bill = useAction(
    () => post<{ id: number; number: string }>(`/api/purchase-orders/${order.id}/bill`, { supplier_ref: ref || null, bill_date: date }),
    (r) => `Bill ${r.number} recorded.`,
  );
  const amount = order.lines.reduce((s, l) => s + (l.qty_received - l.qty_billed) * l.unit_cost, 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record supplier bill</DialogTitle>
          <DialogDescription>
            Bills everything received and not billed yet: {money(amount)} before VAT. The due date follows {order.supplier.name}&apos;s
            payment terms.
          </DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="bill-ref">Supplier&apos;s invoice number</FieldLabel>
            <Input id="bill-ref" placeholder="e.g. INV/2026/0042" value={ref} onChange={(e) => setRef(e.target.value)} />
            <FieldDescription>Helps match the payment later.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="bill-date">Bill date</FieldLabel>
            <Input id="bill-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Back</Button>
          <Button
            disabled={bill.isPending}
            onClick={async () => {
              const r = await bill.mutateAsync();
              onOpenChange(false);
              router.push(`/finance/invoices/${r.id}`);
            }}
          >
            {bill.isPending && <Spinner />} Record bill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
