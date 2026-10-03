"use client";

import { Pencil, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActivityTimeline } from "@/components/erp/activity";
import { Details, PageHeader, StatCard, StatusBadge } from "@/components/erp/common";
import { PartnerSheet } from "@/components/erp/partner-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan } from "@/lib/auth";
import { dateLabel, money, qty } from "@/lib/format";
import type { CustomerDetail, SupplierDetail } from "@/lib/types";

/** Shared detail page for a customer or a supplier. */
export function PartnerDetail({ kind, partner }: { kind: "customer" | "supplier"; partner: CustomerDetail | SupplierDetail }) {
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const customer = kind === "customer" ? (partner as CustomerDetail) : null;
  const supplier = kind === "supplier" ? (partner as SupplierDetail) : null;
  const ordersBase = customer ? "/sales/orders" : "/purchasing/orders";
  const writable = can(customer ? "sales.write" : "purchasing.write");
  const docs = customer ? customer.recent_invoices : supplier!.recent_bills;

  return (
    <>
      <PageHeader
        title={partner.name}
        badge={
          <>
            {customer?.group && (
              <Badge variant="secondary">
                {customer.group.name}
                {customer.group.discount_pct > 0 && ` · −${customer.group.discount_pct}%`}
              </Badge>
            )}
            {!partner.active && <StatusBadge status="inactive" />}
          </>
        }
        description={<span className="font-mono">{partner.code}</span>}
        actions={
          writable && (
            <>
              <Button variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              {partner.active && (
                <Button render={<Link href={`${ordersBase}/new`} />} nativeButton={false}>
                  <Plus /> New order
                </Button>
              )}
            </>
          )
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label={customer ? "Owes us" : "We owe"}
          value={money(partner.balance)}
          hint={partner.overdue ? `${money(partner.overdue)} overdue` : "Nothing overdue"}
          tone={partner.overdue ? "danger" : "success"}
        />
        {customer ? (
          <StatCard
            label="Credit used"
            value={customer.credit_limit ? `${Math.round((customer.credit_used / customer.credit_limit) * 100)}%` : "No limit"}
            hint={customer.credit_limit ? `${money(customer.credit_used)} of ${money(customer.credit_limit)}` : `${money(customer.credit_used)} open orders + invoices`}
            tone={customer.credit_limit && customer.credit_used > customer.credit_limit * 0.9 ? "danger" : undefined}
          />
        ) : (
          <StatCard label="Payment terms" value={`${partner.payment_terms_days} days`} />
        )}
        <StatCard
          label={customer ? "Lifetime sales" : "Lifetime purchases"}
          value={money(customer ? customer.lifetime_revenue : supplier!.lifetime_spend)}
          hint="Excluding VAT"
        />
        {customer && (
          <StatCard
            label="Loyalty points"
            value={qty(customer.loyalty_points)}
            hint={`Earned at the POS tills · pays in ${partner.payment_terms_days} days`}
          />
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card>
            <CardContent>
              <Details
                items={[
                  { label: "Email", value: partner.email },
                  { label: "Phone", value: partner.phone },
                  { label: "City", value: partner.city },
                  { label: "Address", value: partner.address },
                ]}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Recent orders</CardTitle>
            </CardHeader>
            <CardContent>
              <DocTable
                rows={partner.recent_orders.map((o) => ({ ...o, href: `${ordersBase}/${o.id}`, date: o.order_date }))}
                empty="No orders yet."
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{customer ? "Recent invoices" : "Recent bills"}</CardTitle>
            </CardHeader>
            <CardContent>
              <DocTable
                rows={docs.map((i) => ({
                  ...i,
                  href: `/finance/invoices/${i.id}`,
                  date: i.issue_date,
                  status: i.status === "open" && i.due_date < new Date().toISOString().slice(0, 10) ? "overdue" : i.status,
                  extra: i.status === "open" ? `${money(i.balance)} open · due ${dateLabel(i.due_date)}` : undefined,
                }))}
                empty="Nothing invoiced yet."
              />
            </CardContent>
          </Card>
        </div>
        <ActivityTimeline items={partner.activity} />
      </div>
      <PartnerSheet kind={kind} open={editing} onOpenChange={setEditing} partner={partner} />
    </>
  );
}

function DocTable({
  rows,
  empty,
}: {
  rows: { id: number; number: string; href: string; date: string; status: string; total: number; extra?: string }[];
  empty: string;
}) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Number</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell>
              <Link href={r.href} className="font-mono text-xs hover:underline">{r.number}</Link>
            </TableCell>
            <TableCell>{dateLabel(r.date)}</TableCell>
            <TableCell>
              <StatusBadge status={r.status} />
              {r.extra && <p className="mt-1 text-xs text-muted-foreground">{r.extra}</p>}
            </TableCell>
            <TableCell className="text-right tabular-nums">{money(r.total)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
