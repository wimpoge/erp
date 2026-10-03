"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { dateLabel, qty } from "@/lib/format";
import type { Adjustment } from "@/lib/types";

export default function AdjustmentsPage() {
  const can = useCan();
  const newButton = can("inventory.write") && (
    <Button render={<Link href="/inventory/adjustments/new" />} nativeButton={false}>
      <Plus /> New stock count
    </Button>
  );
  return (
    <>
      <PageHeader title="Stock counts" description="Physical counts that correct the system's quantities (damage, loss, miscounts)." actions={newButton} />
      <DataTable<Adjustment>
        endpoint="/api/adjustments"
        rowHref={(a) => `/inventory/adjustments/${a.id}`}
        searchPlaceholder="Number or reason…"
        filters={[
          {
            key: "status",
            label: "Statuses",
            options: [
              { value: "draft", label: "Draft" },
              { value: "done", label: "Done" },
              { value: "cancelled", label: "Cancelled" },
            ],
          },
        ]}
        empty={{ title: "No stock counts yet", action: newButton || undefined }}
        columns={[
          { key: "number", header: "Number", sort: "number", cell: (a) => <span className="font-mono text-xs">{a.number}</span> },
          { key: "date", header: "Date", sort: "date", cell: (a) => dateLabel(a.adjustment_date) },
          { key: "warehouse", header: "Warehouse", cell: (a) => a.warehouse.name },
          { key: "reason", header: "Reason", cell: (a) => a.reason },
          { key: "products", header: "Products", align: "right", hideBelow: "md", cell: (a) => qty(a.products) },
          { key: "by", header: "By", hideBelow: "lg", cell: (a) => a.created_by?.name ?? "—" },
          { key: "status", header: "Status", cell: (a) => <StatusBadge status={a.status} /> },
        ]}
      />
    </>
  );
}
