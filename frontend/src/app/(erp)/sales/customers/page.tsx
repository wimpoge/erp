"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { DataTable } from "@/components/erp/data-table";
import { PartnerSheet } from "@/components/erp/partner-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { get } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Customer, CustomerGroup } from "@/lib/types";

export default function CustomersPage() {
  const can = useCan();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const { data: groups } = useQuery({ queryKey: ["customer-groups"], queryFn: () => get<CustomerGroup[]>("/api/customer-groups") });
  const newButton = can("sales.write") && (
    <Button onClick={() => setCreating(true)}>
      <Plus /> New customer
    </Button>
  );

  return (
    <>
      <PageHeader title="Customers" description="Who buys from us, what they owe, and their terms." actions={newButton} />
      <DataTable<Customer>
        endpoint="/api/customers"
        rowHref={(c) => `/sales/customers/${c.id}`}
        searchPlaceholder="Name, code, email or phone…"
        filters={[
          { key: "group_id", label: "Groups", options: (groups ?? []).map((g) => ({ value: String(g.id), label: g.name })) },
          { key: "overdue", label: "Balances", options: [{ value: "true", label: "With overdue invoices" }] },
          {
            key: "active",
            label: "Customers",
            defaultValue: "true",
            options: [{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }],
          },
        ]}
        empty={{ title: "No customers yet", action: newButton || undefined }}
        columns={[
          { key: "name", header: "Name", sort: "name", cell: (c) => c.name },
          { key: "code", header: "Code", sort: "code", hideBelow: "md", cell: (c) => <span className="font-mono text-xs">{c.code}</span> },
          { key: "group", header: "Group", cell: (c) => (c.group ? <Badge variant="secondary">{c.group.name}</Badge> : "—") },
          { key: "city", header: "City", sort: "city", hideBelow: "lg", cell: (c) => c.city ?? "—" },
          { key: "terms", header: "Terms", hideBelow: "lg", cell: (c) => `${c.payment_terms_days} days` },
          { key: "status", header: "", hideBelow: "md", cell: (c) => (c.active ? null : <StatusBadge status="inactive" />) },
          {
            key: "balance",
            header: "Balance",
            align: "right",
            cell: (c) => (
              <span>
                {money(c.balance)}
                {c.overdue > 0 && <span className="block text-xs text-destructive">{money(c.overdue)} overdue</span>}
              </span>
            ),
          },
        ]}
      />
      <PartnerSheet kind="customer" open={creating} onOpenChange={setCreating} onSaved={(c) => router.push(`/sales/customers/${c.id}`)} />
    </>
  );
}
