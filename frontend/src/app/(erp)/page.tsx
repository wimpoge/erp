"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Boxes, HandCoins, PackageCheck, Receipt, TrendingUp, Truck, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { PageHeader, StatCard } from "@/components/erp/common";
import { MoneyBarChart } from "@/components/erp/money-chart";
import { NAV } from "@/components/erp/nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useCan, useMe } from "@/lib/auth";
import { money, moneyShort, monthLabel, qty, relative } from "@/lib/format";
import { entityHref } from "@/lib/links";
import type { Activity, Dashboard } from "@/lib/types";

export default function DashboardPage() {
  const me = useMe();
  const can = useCan();
  const router = useRouter();
  const allowed = can("reports.read");

  // Roles without reports (e.g. warehouse) land on their first screen instead.
  useEffect(() => {
    if (!allowed) {
      // Warehouse staff start at the stock; anyone else at their first menu item.
      const first = me.permissions.includes("inventory.write")
        ? "/inventory/stock"
        : NAV.flatMap((g) => g.items).find((i) => me.permissions.includes(i.permission))?.href;
      router.replace(first ?? "/inventory/stock");
    }
  }, [allowed, me, router]);

  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => get<Dashboard>("/api/reports/dashboard"),
    enabled: allowed,
  });
  const { data: activity } = useQuery({
    queryKey: ["activity"],
    queryFn: () => get<Activity[]>("/api/reports/activity", { limit: 8 }),
    enabled: allowed,
  });
  if (!allowed) return null;

  const change = data && data.revenue_prev_30d ? ((data.revenue_30d - data.revenue_prev_30d) / data.revenue_prev_30d) * 100 : 0;
  const margin = data && data.revenue_30d ? (data.gross_profit_30d / data.revenue_30d) * 100 : 0;

  return (
    <>
      <PageHeader
        title={`Good ${greeting()}, ${me.username}`}
        description="How the business is doing over the last 30 days."
        actions={
          <>
            {can("sales.write") && (
              <Button render={<Link href="/sales/orders/new" />} nativeButton={false}>
                New sales order
              </Button>
            )}
            {can("purchasing.write") && (
              <Button variant="outline" render={<Link href="/purchasing/orders/new" />} nativeButton={false}>
                New purchase order
              </Button>
            )}
          </>
        }
      />

      {!data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Revenue"
            icon={<TrendingUp />}
            value={moneyShort(data.revenue_30d)}
            hint={`${change >= 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(1)}% vs previous 30 days`}
            tone={change >= 0 ? "success" : "danger"}
          />
          <StatCard
            label="Gross profit"
            icon={<HandCoins />}
            value={moneyShort(data.gross_profit_30d)}
            hint={`${margin.toFixed(1)}% margin on goods sold`}
          />
          <StatCard
            label="Receivables"
            icon={<Receipt />}
            value={moneyShort(data.receivables.amount)}
            hint={
              data.receivables.overdue_count ? (
                <Link className="hover:underline" href="/finance/invoices?status=overdue">
                  {moneyShort(data.receivables.overdue)} overdue on {data.receivables.overdue_count} invoice(s) →
                </Link>
              ) : (
                "Nothing overdue"
              )
            }
            tone={data.receivables.overdue_count ? "danger" : "success"}
          />
          <StatCard
            label="Payables"
            icon={<Wallet />}
            value={moneyShort(data.payables.amount)}
            hint={
              data.payables.overdue_count
                ? `${moneyShort(data.payables.overdue)} overdue on ${data.payables.overdue_count} bill(s)`
                : `${data.payables.count} open bill(s), none overdue`
            }
            tone={data.payables.overdue_count ? "danger" : undefined}
          />
          <StatCard label="Stock value" icon={<Boxes />} value={moneyShort(data.stock_value)} hint="At moving average cost" />
          <StatCard
            label="Orders to ship"
            icon={<PackageCheck />}
            value={qty(data.orders_to_deliver)}
            hint={
              <Link className="hover:underline" href="/sales/orders?status=open">
                See open sales orders →
              </Link>
            }
          />
          <StatCard
            label="Orders to receive"
            icon={<Truck />}
            value={qty(data.orders_to_receive)}
            hint={
              <Link className="hover:underline" href="/purchasing/orders?status=open">
                See open purchase orders →
              </Link>
            }
          />
          <StatCard
            label="Low stock"
            icon={<AlertTriangle />}
            value={qty(data.low_stock.length)}
            hint={data.low_stock.length ? "Products at or under their reorder point" : "Everything above reorder point"}
            tone={data.low_stock.length ? "danger" : "success"}
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Sales and gross profit</CardTitle>
            <CardDescription>Invoiced sales (excl. tax) and profit after cost of goods, last 12 months</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" render={<Link href="/reports" />} nativeButton={false}>
                Reports →
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {data ? (
              <MoneyBarChart
                data={data.monthly}
                xKey="month"
                xFormat={monthLabel}
                series={[
                  { key: "revenue", label: "Sales" },
                  { key: "gross_profit", label: "Gross profit" },
                ]}
              />
            ) : (
              <Skeleton className="h-70" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Low stock</CardTitle>
            <CardDescription>Company-wide stock at or below the reorder point</CardDescription>
            {can("purchasing.write") && (
              <CardAction>
                <Button size="sm" variant="outline" render={<Link href="/purchasing/orders/new" />} nativeButton={false}>
                  Reorder
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {data?.low_stock.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing to reorder right now.</p>
            ) : (
              <ul className="divide-y">
                {data?.low_stock.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <Link href={`/inventory/products/${p.id}`} className="block truncate text-sm font-medium hover:underline">
                        {p.name}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {p.sku} · reorder at {qty(p.reorder_point)}
                      </p>
                    </div>
                    <Badge variant={p.on_hand === 0 ? "destructive" : "outline"} className="tabular-nums">
                      {qty(p.on_hand)} left
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Best sellers</CardTitle>
            <CardDescription>Top products by invoiced sales, last 3 months</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-right">Units</TableHead>
                  <TableHead className="text-right">Sales</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.top_products.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <Link href={`/inventory/products/${p.id}`} className="font-medium hover:underline">
                        {p.name}
                      </Link>
                      <p className="text-xs text-muted-foreground">{p.sku}</p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.qty)}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(p.revenue)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Across all modules</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {activity
                ? activity.map((a) => {
                    const href = entityHref(a.entity_type, a.entity_id);
                    return (
                      <li key={a.id} className="text-sm">
                        {href ? (
                          <Link href={href} className="line-clamp-2 hover:underline">
                            {a.message}
                          </Link>
                        ) : (
                          <p className="line-clamp-2">{a.message}</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {a.user?.name ?? "Integration API"} · {relative(a.at)}
                        </p>
                      </li>
                    );
                  })
                : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-9" />)}
            </ol>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 11 ? "morning" : h < 15 ? "afternoon" : "evening";
}
