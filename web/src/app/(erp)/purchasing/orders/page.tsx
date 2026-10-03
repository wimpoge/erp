"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader, Progress, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { dateLabel, money } from "@/lib/format";
import type { PurchaseOrder } from "@/lib/types";

export default function PurchaseOrdersPage() {
  const can = useCan();
  const newButton = can("purchasing.write") && (
    <Button render={<Link href="/purchasing/orders/new" />} nativeButton={false}>
      <Plus /> New purchase order
    </Button>
  );
  return (
    <>
      <PageHeader title="Purchase orders" description="What we ordered from suppliers, what arrived, and what they billed." actions={newButton} />
      <DataTable<PurchaseOrder>
        endpoint="/api/purchase-orders"
        rowHref={(o) => `/purchasing/orders/${o.id}`}
        searchPlaceholder="Order number, supplier or reference…"
        filters={[
          {
            key: "status",
            label: "Statuses",
            options: [
              { value: "open", label: "To receive" },
              { value: "draft", label: "Draft" },
              { value: "confirmed", label: "Confirmed" },
              { value: "partially_received", label: "Partly received" },
              { value: "received", label: "Received" },
              { value: "cancelled", label: "Cancelled" },
            ],
          },
        ]}
        empty={{ title: "No purchase orders yet", description: "Order stock from a supplier.", action: newButton || undefined }}
        columns={[
          { key: "number", header: "Number", sort: "number", cell: (o) => <span className="font-mono text-xs">{o.number}</span> },
          { key: "date", header: "Date", sort: "date", cell: (o) => dateLabel(o.order_date) },
          { key: "supplier", header: "Supplier", sort: "supplier", cell: (o) => o.supplier.name },
          { key: "warehouse", header: "To", hideBelow: "lg", cell: (o) => o.warehouse.code },
          { key: "expected", header: "Expected", hideBelow: "lg", cell: (o) => dateLabel(o.expected_date) },
          { key: "status", header: "Status", cell: (o) => <StatusBadge status={o.status} /> },
          {
            key: "received",
            header: "Received",
            hideBelow: "md",
            cell: (o) => (o.status === "draft" || o.status === "cancelled" ? "—" : <Progress value={o.received_pct} />),
          },
          { key: "billing", header: "Billing", hideBelow: "lg", cell: (o) => <StatusBadge status={o.billing_status} /> },
          { key: "total", header: "Total", sort: "total", align: "right", cell: (o) => money(o.total) },
        ]}
      />
    </>
  );
}
