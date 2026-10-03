"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { PartnerSheet } from "@/components/erp/partner-sheet";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Supplier } from "@/lib/types";

export default function SuppliersPage() {
  const can = useCan();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const newButton = can("purchasing.write") && (
    <Button onClick={() => setCreating(true)}>
      <Plus /> New supplier
    </Button>
  );

  return (
    <>
      <PageHeader title="Suppliers" description="Who we buy from, their terms, and what we owe them." actions={newButton} />
      <DataTable<Supplier>
        endpoint="/api/suppliers"
        rowHref={(s) => `/purchasing/suppliers/${s.id}`}
        searchPlaceholder="Name, code or email…"
        filters={[
          {
            key: "active",
            label: "Suppliers",
            defaultValue: "true",
            options: [{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }],
          },
        ]}
        empty={{ title: "No suppliers yet", action: newButton || undefined }}
        columns={[
          { key: "name", header: "Name", sort: "name", cell: (s) => s.name },
          { key: "code", header: "Code", sort: "code", hideBelow: "md", cell: (s) => <span className="font-mono text-xs">{s.code}</span> },
          { key: "city", header: "City", sort: "city", hideBelow: "md", cell: (s) => s.city ?? "—" },
          { key: "email", header: "Email", hideBelow: "lg", cell: (s) => s.email ?? "—" },
          { key: "terms", header: "Terms", cell: (s) => `${s.payment_terms_days} days` },
          { key: "status", header: "", hideBelow: "md", cell: (s) => (s.active ? null : <StatusBadge status="inactive" />) },
          {
            key: "balance",
            header: "We owe",
            align: "right",
            cell: (s) => (
              <span>
                {money(s.balance)}
                {s.overdue > 0 && <span className="block text-xs text-destructive">{money(s.overdue)} overdue</span>}
              </span>
            ),
          },
        ]}
      />
      <PartnerSheet kind="supplier" open={creating} onOpenChange={setCreating} onSaved={(s) => router.push(`/purchasing/suppliers/${s.id}`)} />
    </>
  );
}
