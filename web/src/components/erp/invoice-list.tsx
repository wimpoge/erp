"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader, StatCard, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { get } from "@/lib/api";
import { dateLabel, money, moneyShort } from "@/lib/format";
import type { Invoice } from "@/lib/types";

type Aging = { buckets: string[]; totals: Record<string, number> };

/** Customer invoices (receivables) or supplier bills (payables). */
export function InvoiceList({ kind }: { kind: "customer" | "supplier" }) {
  const customer = kind === "customer";
  const { data: aging } = useQuery({
    queryKey: ["aging", kind],
    queryFn: () => get<Aging>("/api/reports/aging", { kind }),
  });
  const total = aging ? Object.values(aging.totals).reduce((a, b) => a + b, 0) : 0;
  const overdue = aging ? total - aging.totals.current : 0;

  return (
    <>
      <PageHeader
        title={customer ? "Customer invoices" : "Supplier bills"}
        description={
          customer
            ? "What customers owe us. Invoices are created from delivered sales orders."
            : "What we owe suppliers. Bills are recorded against received purchase orders."
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={customer ? "Total receivable" : "Total payable"} value={moneyShort(total)} />
        <StatCard label="Not yet due" value={moneyShort(aging?.totals.current ?? 0)} />
        <StatCard
          label="Overdue"
          value={moneyShort(overdue)}
          tone={overdue ? "danger" : "success"}
          hint={aging ? `1–30 days ${moneyShort(aging.totals["1-30"])} · 31+ days ${moneyShort(overdue - aging.totals["1-30"])}` : undefined}
        />
        <StatCard label="Over 90 days" value={moneyShort(aging?.totals["90+"] ?? 0)} tone={aging?.totals["90+"] ? "danger" : undefined}
          hint="Chase or write off" />
      </div>
      <DataTable<Invoice>
        endpoint="/api/invoices"
        params={{ kind }}
        rowHref={(i) => `/finance/${customer ? "invoices" : "bills"}/${i.id}`}
        searchPlaceholder={customer ? "Invoice number, customer or reference…" : "Bill number, supplier or their invoice no…"}
        filters={[
          {
            key: "status",
            label: "Statuses",
            options: [
              { value: "unpaid", label: "Unpaid" },
              { value: "overdue", label: "Overdue" },
              { value: "paid", label: "Paid" },
              { value: "cancelled", label: "Cancelled" },
            ],
          },
        ]}
        columns={[
          { key: "number", header: "Number", sort: "number", cell: (i) => <span className="font-mono text-xs">{i.number}</span> },
          { key: "partner", header: customer ? "Customer" : "Supplier", sort: "partner", cell: (i) => i.partner.name },
          ...(customer ? [] : [{ key: "ref", header: "Their ref.", hideBelow: "lg" as const, cell: (i: Invoice) => i.partner_ref ?? "—" }]),
          { key: "date", header: "Issued", sort: "date", hideBelow: "md", cell: (i) => dateLabel(i.issue_date) },
          {
            key: "due",
            header: "Due",
            sort: "due",
            cell: (i) => (
              <span>
                {dateLabel(i.due_date)}
                {i.days_overdue > 0 && <span className="block text-xs text-destructive">{i.days_overdue} days late</span>}
              </span>
            ),
          },
          { key: "status", header: "Status", cell: (i) => <StatusBadge status={i.status} /> },
          { key: "total", header: "Total", sort: "total", align: "right", hideBelow: "md", cell: (i) => money(i.total) },
          { key: "balance", header: "Open", sort: "balance", align: "right", cell: (i) => (i.balance ? money(i.balance) : "—") },
        ]}
      />
    </>
  );
}
