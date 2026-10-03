"use client";

import { useQuery } from "@tanstack/react-query";
import { Printer, Wallet } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { ActivityTimeline } from "@/components/erp/activity";
import { InvoiceDocument } from "@/components/erp/invoice-document";
import { ConfirmButton, Details, PageHeader, StatCard, StatusBadge, Totals } from "@/components/erp/common";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, get, post } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { dateLabel, money, qty, todayIso } from "@/lib/format";
import { useAction, useCompany } from "@/lib/hooks";
import type { InvoiceDetail } from "@/lib/types";

const METHODS = [
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "qris", label: "QRIS" },
];

export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const [paying, setPaying] = useState(false);
  const { data: company } = useCompany();
  const { data: inv } = useQuery({ queryKey: ["/api/invoices", id], queryFn: () => get<InvoiceDetail>(`/api/invoices/${id}`) });
  const cancel = useAction(() => post(`/api/invoices/${id}/cancel`), "Cancelled.");
  if (!inv) return <Skeleton className="h-[600px]" />;

  const customer = inv.kind === "customer";
  const word = customer ? "invoice" : "bill";
  const partnerHref = customer ? `/sales/customers/${inv.partner.id}` : `/purchasing/suppliers/${inv.partner.id}`;
  const sourceHref = inv.source && (inv.source.type === "sales_order" ? `/sales/orders/${inv.source.id}` : `/purchasing/orders/${inv.source.id}`);
  const open = inv.status === "open" || inv.status === "partially_paid" || inv.status === "overdue";

  return (
    <>
      <PageHeader
        title={<span className="font-mono">{inv.number}</span>}
        badge={<StatusBadge status={inv.status} />}
        description={
          <>
            {customer ? "Invoice to " : "Bill from "}
            <Link href={partnerHref} className="font-medium text-foreground hover:underline">{inv.partner.name}</Link>
          </>
        }
        actions={
          <>
            <Button variant="outline" onClick={() => window.print()} className="print:hidden">
              <Printer /> Print
            </Button>
            {open && inv.amount_paid === 0 && can("finance.write") && (
              <ConfirmButton variant="ghost" destructive title={`Cancel ${inv.number}?`}
                description={`The ${word} is voided and its quantities can be ${customer ? "invoiced" : "billed"} again from the order.`}
                confirmLabel={`Cancel ${word}`} onConfirm={() => cancel.mutateAsync()}>
                Cancel {word}
              </ConfirmButton>
            )}
            {open && can("finance.write") && (
              <Button onClick={() => setPaying(true)} className="print:hidden">
                <Wallet /> {customer ? "Register payment" : "Pay bill"}
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3 print:hidden">
        <StatCard label="Total" value={money(inv.total)} />
        <StatCard label={customer ? "Received" : "Paid"} value={money(inv.amount_paid)} />
        <StatCard
          label="Open balance"
          value={money(inv.balance)}
          tone={inv.days_overdue ? "danger" : inv.balance === 0 ? "success" : undefined}
          hint={inv.days_overdue ? `${inv.days_overdue} days past due` : inv.balance ? `Due ${dateLabel(inv.due_date)}` : "Settled"}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px] print:hidden">
        <div className="space-y-6">
          <Card>
            <CardContent className="space-y-6">
              <Details
                items={[
                  { label: customer ? "Customer" : "Supplier", value: <Link href={partnerHref} className="hover:underline">{inv.partner.name}</Link> },
                  { label: "Issued", value: dateLabel(inv.issue_date) },
                  { label: "Due", value: dateLabel(inv.due_date) },
                  { label: customer ? "Customer reference" : "Supplier's invoice no.", value: inv.partner_ref },
                  ...(inv.source && sourceHref ? [{ label: "Order", value: <Link href={sourceHref} className="font-mono text-xs hover:underline">{inv.source.number}</Link> }] : []),
                  { label: "Created by", value: inv.created_by?.name },
                ]}
              />
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">{customer ? "Price" : "Cost"}</TableHead>
                    {customer && <TableHead className="text-right">Disc.</TableHead>}
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {inv.lines.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>
                        <p className="font-medium">{l.product.name}</p>
                        <p className="text-xs text-muted-foreground">{l.product.sku}</p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{qty(l.qty)}</TableCell>
                      <TableCell className="text-right tabular-nums">{money(l.unit_price)}</TableCell>
                      {customer && <TableCell className="text-right tabular-nums">{l.discount_pct ? `${l.discount_pct}%` : "—"}</TableCell>}
                      <TableCell className="text-right tabular-nums">{money(l.line_total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Totals
                rows={[
                  { label: "Subtotal", value: money(inv.subtotal) },
                  { label: `VAT ${inv.tax_rate}%`, value: money(inv.tax) },
                  { label: "Total", value: money(inv.total), strong: true },
                  ...(inv.amount_paid ? [{ label: customer ? "Received" : "Paid", value: `−${money(inv.amount_paid)}` }] : []),
                  ...(inv.amount_paid ? [{ label: "Balance due", value: money(inv.balance), strong: true }] : []),
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Payments</CardTitle>
            </CardHeader>
            <CardContent>
              {inv.payments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No payments yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Number</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Method</TableHead>
                      <TableHead>Reference</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inv.payments.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-mono text-xs">{p.number}</TableCell>
                        <TableCell>{dateLabel(p.payment_date)}</TableCell>
                        <TableCell>{METHODS.find((m) => m.value === p.method)?.label ?? p.method}</TableCell>
                        <TableCell className="text-muted-foreground">{p.reference ?? "—"}</TableCell>
                        <TableCell className="text-right tabular-nums">{money(p.amount)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
        <ActivityTimeline items={inv.activity} />
      </div>
      <InvoiceDocument invoice={inv} company={company} />
      <PaymentDialog open={paying} onOpenChange={setPaying} invoice={inv} />
    </>
  );
}

function PaymentDialog({ open, onOpenChange, invoice }: { open: boolean; onOpenChange: (o: boolean) => void; invoice: InvoiceDetail }) {
  const customer = invoice.kind === "customer";
  const [amount, setAmount] = useState(invoice.balance);
  const [date, setDate] = useState(todayIso());
  const [method, setMethod] = useState("bank_transfer");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setAmount(invoice.balance);
      setDate(todayIso());
      setReference("");
      setError(null);
    }
  }
  const pay = useAction(
    () => post<InvoiceDetail>(`/api/invoices/${invoice.id}/payments`, { amount, payment_date: date, method, reference: reference || null }),
    (r) => (r.balance === 0 ? `${r.number} is fully paid.` : `Payment recorded; ${money(r.balance)} still open on ${r.number}.`),
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await pay.mutateAsync();
      onOpenChange(false);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{customer ? "Register payment received" : "Record payment to supplier"}</DialogTitle>
            <DialogDescription>
              {invoice.number} · open balance {money(invoice.balance)}. A smaller amount leaves the rest open.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="pay-amount">Amount (Rp)</FieldLabel>
              <Input id="pay-amount" type="number" min={1} max={invoice.balance} required value={amount}
                onChange={(e) => setAmount(Math.floor(Number(e.target.value)))} className="tabular-nums" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="pay-date">Date</FieldLabel>
                <Input id="pay-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
              </Field>
              <Field>
                <FieldLabel>Method</FieldLabel>
                <Select items={METHODS} value={method} onValueChange={(v) => setMethod(String(v))}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {METHODS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="pay-ref">Reference</FieldLabel>
              <Input id="pay-ref" placeholder="Bank transaction id, receipt no…" value={reference} onChange={(e) => setReference(e.target.value)} />
            </Field>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Back</Button>
            <Button type="submit" disabled={pay.isPending}>{pay.isPending && <Spinner />} Save payment</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
