"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { money, moneyShort } from "@/lib/format";

/**
 * Bars of rupiah amounts over a category axis. One y-axis only; every series is money.
 * A legend appears from two series up; hovering shows exact amounts.
 */
export function MoneyBarChart({
  data,
  xKey,
  xFormat = String,
  series,
  layout = "vertical",
  height = 280,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  xKey: string;
  xFormat?: (v: string) => string;
  series: { key: string; label: string }[];
  /** "vertical" = columns over time; "horizontal" = ranked bars with long labels. */
  layout?: "vertical" | "horizontal";
  height?: number;
}) {
  const config = Object.fromEntries(
    series.map((s, i) => [s.key, { label: s.label, color: `var(--chart-${i + 1})` }]),
  ) satisfies ChartConfig;
  const horizontal = layout === "horizontal";

  return (
    <ChartContainer config={config} className="w-full" style={{ height }}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} barGap={2} margin={{ left: 4, right: 8 }}>
        <CartesianGrid vertical={horizontal} horizontal={!horizontal} strokeDasharray="3 3" />
        {horizontal ? (
          <>
            <XAxis type="number" tickFormatter={moneyShort} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey={xKey} width={150} tickLine={false} axisLine={false}
              tickFormatter={xFormat} interval={0} tick={{ fontSize: 12 }} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tickFormatter={xFormat} tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis tickFormatter={moneyShort} tickLine={false} axisLine={false} width={72} />
          </>
        )}
        <ChartTooltip
          cursor={{ fill: "var(--muted)", opacity: 0.6 }}
          content={
            <ChartTooltipContent
              labelFormatter={(v) => xFormat(String(v))}
              formatter={(value, name, item) => (
                <div className="flex w-full items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: item.color }} />
                  <span className="text-muted-foreground">{config[name as string]?.label ?? name}</span>
                  <span className="ml-auto font-medium tabular-nums text-foreground">{money(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        {series.length > 1 && <ChartLegend itemSorter={null} content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} fill={`var(--color-${s.key})`} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={horizontal ? 22 : 28} />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
