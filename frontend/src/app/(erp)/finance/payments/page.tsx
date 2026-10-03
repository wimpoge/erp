"use client";

import Link from "next/link";
import { PageHeader } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Badge } from "@/components/ui/badge";
import { dateLabel, money } from "@/lib/format";
import type { CodeRef, Payment } from "@/lib/types";

type PaymentRow = Payment & {
  direction: "in" | "out";
  invoice: { id: number; number: string; kind: string };
  partner: CodeRef;
};

const METHOD: Record<string, string> = { bank_transfer: "Bank transfer", cash: "Cash", card: "Card", qris: "QRIS" };

export default function PaymentsPage() {
  return (
    <>
      <PageHeader title="Payments" description="Money received from customers and paid to suppliers." />
      <DataTable<PaymentRow>
        endpoint="/api/payments"
        searchPlaceholder="Payment, invoice number or reference…"
        filters={[
          {
            key: "kind",
            label: "Directions",
            options: [
              { value: "customer", label: "Received from customers" },
              { value: "supplier", label: "Paid to suppliers" },
            ],
          },
        ]}
        columns={[
          { key: "number", header: "Number", cell: (p) => <span className="font-mono text-xs">{p.number}</span> },
          { key: "date", header: "Date", sort: "date", cell: (p) => dateLabel(p.payment_date) },
          {
            key: "direction",
            header: "Direction",
            cell: (p) => <Badge variant={p.direction === "in" ? "secondary" : "outline"}>{p.direction === "in" ? "Received" : "Paid"}</Badge>,
          },
          { key: "partner", header: "Customer / supplier", cell: (p) => p.partner.name },
          {
            key: "invoice",
            header: "For",
            cell: (p) => (
              <Link href={`/finance/invoices/${p.invoice.id}`} className="font-mono text-xs hover:underline">{p.invoice.number}</Link>
            ),
          },
          { key: "method", header: "Method", hideBelow: "md", cell: (p) => METHOD[p.method] ?? p.method },
          { key: "reference", header: "Reference", hideBelow: "lg", cell: (p) => p.reference ?? "—" },
          {
            key: "amount",
            header: "Amount",
            sort: "amount",
            align: "right",
            cell: (p) => (
              <span className={p.direction === "in" ? "text-emerald-700 dark:text-emerald-400" : undefined}>
                {p.direction === "in" ? "+" : "−"}
                {money(p.amount)}
              </span>
            ),
          },
        ]}
      />
    </>
  );
}
