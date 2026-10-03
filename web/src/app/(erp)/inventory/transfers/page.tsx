"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { dateLabel, qty } from "@/lib/format";
import type { Transfer } from "@/lib/types";

export default function TransfersPage() {
  const can = useCan();
  const newButton = can("inventory.write") && (
    <Button render={<Link href="/inventory/transfers/new" />} nativeButton={false}>
      <Plus /> New transfer
    </Button>
  );
  return (
    <>
      <PageHeader title="Transfers" description="Stock moved between warehouses, e.g. from the distribution center to a store." actions={newButton} />
      <DataTable<Transfer>
        endpoint="/api/transfers"
        rowHref={(t) => `/inventory/transfers/${t.id}`}
        searchPlaceholder="Transfer number…"
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
        empty={{ title: "No transfers yet", action: newButton || undefined }}
        columns={[
          { key: "number", header: "Number", sort: "number", cell: (t) => <span className="font-mono text-xs">{t.number}</span> },
          { key: "date", header: "Date", sort: "date", cell: (t) => dateLabel(t.transfer_date) },
          { key: "route", header: "From → to", cell: (t) => `${t.from_warehouse.name} → ${t.to_warehouse.name}` },
          { key: "units", header: "Units", align: "right", cell: (t) => qty(t.units) },
          { key: "by", header: "By", hideBelow: "lg", cell: (t) => t.created_by?.name ?? "—" },
          { key: "status", header: "Status", cell: (t) => <StatusBadge status={t.status} /> },
        ]}
      />
    </>
  );
}
