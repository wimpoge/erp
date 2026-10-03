"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader, Progress, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { dateLabel, money } from "@/lib/format";
import type { SalesOrder } from "@/lib/types";

export default function SalesOrdersPage() {
  const can = useCan();
  const newButton = can("sales.write") && (
    <Button render={<Link href="/sales/orders/new" />} nativeButton={false}>
      <Plus /> New sales order
    </Button>
  );
  return (
    <>
      <PageHeader title="Sales orders" description="Quotes, confirmed orders and their delivery and invoicing." actions={newButton} />
      <DataTable<SalesOrder>
        endpoint="/api/sales-orders"
        rowHref={(o) => `/sales/orders/${o.id}`}
        searchPlaceholder="Order number, customer or reference…"
        filters={[
          {
            key: "status",
            label: "Statuses",
            options: [
              { value: "open", label: "To deliver" },
              { value: "draft", label: "Draft" },
              { value: "confirmed", label: "Confirmed" },
              { value: "partially_delivered", label: "Partly delivered" },
              { value: "delivered", label: "Delivered" },
              { value: "cancelled", label: "Cancelled" },
            ],
          },
        ]}
        empty={{ title: "No sales orders yet", description: "Create one to sell to a customer.", action: newButton || undefined }}
        columns={[
          { key: "number", header: "Number", sort: "number", cell: (o) => <span className="font-mono text-xs">{o.number}</span> },
          { key: "date", header: "Date", sort: "date", cell: (o) => dateLabel(o.order_date) },
          {
            key: "customer",
            header: "Customer",
            sort: "customer",
            cell: (o) => (
              <span className="flex items-center gap-2">
                {o.customer.name}
                {o.source === "api" && <Badge variant="secondary">API</Badge>}
              </span>
            ),
          },
          { key: "warehouse", header: "From", hideBelow: "lg", cell: (o) => o.warehouse.code },
          { key: "status", header: "Status", cell: (o) => <StatusBadge status={o.status} /> },
          {
            key: "delivered",
            header: "Delivered",
            hideBelow: "md",
            cell: (o) => (o.status === "draft" || o.status === "cancelled" ? "—" : <Progress value={o.delivered_pct} />),
          },
          { key: "invoice", header: "Invoicing", hideBelow: "lg", cell: (o) => <StatusBadge status={o.invoice_status} /> },
          { key: "total", header: "Total", sort: "total", align: "right", cell: (o) => money(o.total) },
        ]}
      />
    </>
  );
}
