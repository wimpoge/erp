"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { PageHeader, StatCard } from "@/components/erp/common";
import { MoneyBarChart } from "@/components/erp/money-chart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get } from "@/lib/api";
import { money, moneyShort, monthLabel, qty } from "@/lib/format";

type Monthly = { month: string; revenue: number; cogs: number; purchases: number; gross_profit: number };
type SalesReport = {
  monthly: Monthly[];
  by_category: { category: string; revenue: number }[];
  top_products: { id: number; sku: string; name: string; qty: number; revenue: number }[];
  top_customers: { id: number; code: string; name: string; invoices: number; revenue: number }[];
};
type InventoryReport = {
  by_warehouse: { id: number; code: string; name: string; units: number; value: number }[];
  total_value: number;
  low_stock: { id: number; sku: string; name: string; on_hand: number; reorder_point: number }[];
};
type Aging = {
  buckets: string[];
  totals: Record<string, number>;
  partners: ({ id: number; name: string; total: number } & Record<string, number>)[];
};

const PERIODS = [
  { value: "3", label: "Last 3 months" },
  { value: "6", label: "Last 6 months" },
  { value: "12", label: "Last 12 months" },
];

export default function ReportsPage() {
  const [months, setMonths] = useState("12");
  return (
    <>
      <PageHeader title="Reports" description="Sales performance, stock value and who owes whom." />
      <Tabs defaultValue="sales">
        <TabsList>
          <TabsTrigger value="sales">Sales</TabsTrigger>
          <TabsTrigger value="inventory">Inventory</TabsTrigger>
          <TabsTrigger value="receivables">Receivables</TabsTrigger>
          <TabsTrigger value="payables">Payables</TabsTrigger>
        </TabsList>
        <TabsContent value="sales" className="mt-4 space-y-4">
          <Select items={PERIODS} value={months} onValueChange={(v) => setMonths(String(v))}>
            <SelectTrigger aria-label="Period" className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              {PERIODS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <SalesTab months={Number(months)} />
        </TabsContent>
        <TabsContent value="inventory" className="mt-4 space-y-4">
          <InventoryTab />
        </TabsContent>
        <TabsContent value="receivables" className="mt-4">
          <AgingTab kind="customer" />
        </TabsContent>
        <TabsContent value="payables" className="mt-4">
          <AgingTab kind="supplier" />
        </TabsContent>
      </Tabs>
    </>
  );
}

function SalesTab({ months }: { months: number }) {
  const { data } = useQuery({ queryKey: ["report-sales", months], queryFn: () => get<SalesReport>("/api/reports/sales", { months }) });
  if (!data) return <Skeleton className="h-[480px]" />;
  const sum = (k: keyof Monthly) => data.monthly.reduce((s, m) => s + (m[k] as number), 0);
  const revenue = sum("revenue"), gp = sum("gross_profit");

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Sales (excl. VAT)" value={moneyShort(revenue)} />
        <StatCard label="Cost of goods sold" value={moneyShort(sum("cogs"))} />
        <StatCard label="Gross profit" value={moneyShort(gp)} hint={revenue ? `${((gp / revenue) * 100).toFixed(1)}% margin` : undefined} />
        <StatCard label="Purchases billed" value={moneyShort(sum("purchases"))} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Sales and cost of goods by month</CardTitle>
          <CardDescription>The gap between the bars is the gross profit</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <MoneyBarChart data={data.monthly} xKey="month" xFormat={monthLabel}
            series={[{ key: "revenue", label: "Sales" }, { key: "cogs", label: "Cost of goods" }]} />
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">Show as table</summary>
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Month</TableHead>
                  <TableHead className="text-right">Sales</TableHead>
                  <TableHead className="text-right">Cost of goods</TableHead>
                  <TableHead className="text-right">Gross profit</TableHead>
                  <TableHead className="text-right">Margin</TableHead>
                  <TableHead className="text-right">Purchases</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.monthly.map((m) => (
                  <TableRow key={m.month}>
                    <TableCell>{monthLabel(m.month)}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(m.revenue)}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(m.cogs)}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(m.gross_profit)}</TableCell>
                    <TableCell className="text-right tabular-nums">{m.revenue ? `${((m.gross_profit / m.revenue) * 100).toFixed(1)}%` : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(m.purchases)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Sales by category</CardTitle>
          </CardHeader>
          <CardContent>
            <MoneyBarChart data={data.by_category} xKey="category" layout="horizontal" height={40 * data.by_category.length + 40}
              series={[{ key: "revenue", label: "Sales" }]} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Top customers</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead className="text-right">Invoices</TableHead>
                  <TableHead className="text-right">Sales</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_customers.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Link href={`/sales/customers/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{qty(c.invoices)}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(c.revenue)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Top products</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="text-right">Units</TableHead>
                <TableHead className="text-right">Sales</TableHead>
                <TableHead className="text-right">Share</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.top_products.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={`/inventory/products/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{p.sku}</TableCell>
                  <TableCell className="text-right tabular-nums">{qty(p.qty)}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(p.revenue)}</TableCell>
                  <TableCell className="text-right tabular-nums">{revenue ? `${((p.revenue / revenue) * 100).toFixed(1)}%` : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}

function InventoryTab() {
  const { data } = useQuery({ queryKey: ["report-inventory"], queryFn: () => get<InventoryReport>("/api/reports/inventory") });
  if (!data) return <Skeleton className="h-[400px]" />;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Stock value by warehouse</CardTitle>
          <CardDescription>At moving average cost · total {money(data.total_value)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <MoneyBarChart data={data.by_warehouse} xKey="name" layout="horizontal" height={50 * data.by_warehouse.length + 40}
            series={[{ key: "value", label: "Stock value" }]} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Warehouse</TableHead>
                <TableHead className="text-right">Units</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="text-right">Share</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.by_warehouse.map((w) => (
                <TableRow key={w.id}>
                  <TableCell>{w.name}</TableCell>
                  <TableCell className="text-right tabular-nums">{qty(w.units)}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(w.value)}</TableCell>
                  <TableCell className="text-right tabular-nums">{data.total_value ? `${((w.value / data.total_value) * 100).toFixed(1)}%` : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Reorder list</CardTitle>
          <CardDescription>Products at or below their reorder point</CardDescription>
        </CardHeader>
        <CardContent>
          {data.low_stock.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing to reorder.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-right">On hand</TableHead>
                  <TableHead className="text-right">Reorder at</TableHead>
                  <TableHead className="text-right">Short by</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.low_stock.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <Link href={`/inventory/products/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                      <p className="font-mono text-xs text-muted-foreground">{p.sku}</p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.on_hand)}</TableCell>
                    <TableCell className="text-right tabular-nums">{qty(p.reorder_point)}</TableCell>
                    <TableCell className="text-right tabular-nums text-destructive">{qty(p.reorder_point - p.on_hand)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const BUCKET_LABEL: Record<string, string> = { current: "Not due", "1-30": "1–30 days", "31-60": "31–60", "61-90": "61–90", "90+": "90+" };

function AgingTab({ kind }: { kind: "customer" | "supplier" }) {
  const { data } = useQuery({ queryKey: ["aging", kind], queryFn: () => get<Aging>("/api/reports/aging", { kind }) });
  if (!data) return <Skeleton className="h-[400px]" />;
  const total = Object.values(data.totals).reduce((a, b) => a + b, 0);
  const base = kind === "customer" ? "/sales/customers" : "/purchasing/suppliers";

  return (
    <Card>
      <CardHeader>
        <CardTitle>{kind === "customer" ? "Receivables aging" : "Payables aging"}</CardTitle>
        <CardDescription>
          Open {kind === "customer" ? "invoices" : "bills"} by days past their due date · total {money(total)}
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {data.partners.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing open.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{kind === "customer" ? "Customer" : "Supplier"}</TableHead>
                {data.buckets.map((b) => (
                  <TableHead key={b} className="text-right">{BUCKET_LABEL[b] ?? b}</TableHead>
                ))}
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.partners.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={`${base}/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                  </TableCell>
                  {data.buckets.map((b) => (
                    <TableCell key={b} className={`text-right tabular-nums ${b !== "current" && p[b] ? "text-destructive" : ""}`}>
                      {p[b] ? money(p[b]) : "—"}
                    </TableCell>
                  ))}
                  <TableCell className="text-right font-medium tabular-nums">{money(p.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>Total</TableCell>
                {data.buckets.map((b) => (
                  <TableCell key={b} className="text-right tabular-nums">{money(data.totals[b])}</TableCell>
                ))}
                <TableCell className="text-right tabular-nums">{money(total)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
