"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Inbox, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReactNode, Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get, Page } from "@/lib/api";
import { qty } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** API sort key; makes the header clickable. */
  sort?: string;
  align?: "right";
  className?: string;
  /** Hide on narrow screens. */
  hideBelow?: "md" | "lg";
};

export type Filter = {
  key: string;
  label: string;
  options: { value: string; label: string }[];
  /** Value used when the URL has none (e.g. "true" for "active only"). */
  defaultValue?: string;
};

type Props<T> = {
  endpoint: string;
  columns: Column<T>[];
  rowHref?: (row: T) => string;
  rowKey?: (row: T) => string | number;
  filters?: Filter[];
  /** Fixed query params (e.g. kind=supplier) not shown as filters. */
  params?: Record<string, string | number | boolean>;
  searchPlaceholder?: string;
  empty?: { title: string; description?: string; action?: ReactNode };
  pageSize?: number;
  toolbar?: ReactNode;
};

export function DataTable<T>(props: Props<T>) {
  return (
    <Suspense fallback={<TableSkeleton columns={props.columns.length} />}>
      <DataTableInner {...props} />
    </Suspense>
  );
}

const ALL = "__all__";

function DataTableInner<T>({
  endpoint,
  columns,
  rowHref,
  rowKey = (row) => (row as { id: number }).id,
  filters = [],
  params = {},
  searchPlaceholder = "Search…",
  empty,
  pageSize = 50,
  toolbar,
}: Props<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const page = Number(search.get("page") ?? 1);
  const sort = search.get("sort") ?? undefined;
  const urlQ = search.get("q") ?? "";
  const [q, setQ] = useState(urlQ);

  const filterValues = Object.fromEntries(
    filters.map((f) => [f.key, search.get(f.key) ?? f.defaultValue ?? ALL]),
  );

  function setParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(search.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }

  // Debounced search into the URL.
  useEffect(() => {
    if (q === urlQ) return;
    const t = setTimeout(() => setParams({ q: q.trim() || null }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const query = {
    ...params,
    page,
    page_size: pageSize,
    sort,
    q: urlQ || undefined,
    ...Object.fromEntries(Object.entries(filterValues).map(([k, v]) => [k, v === ALL ? undefined : v])),
  };
  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: [endpoint, query],
    queryFn: () => get<Page<T>>(endpoint, query),
    placeholderData: keepPreviousData,
  });

  const pages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const hasFilters = urlQ || filters.some((f) => (search.get(f.key) ?? f.defaultValue ?? ALL) !== (f.defaultValue ?? ALL));

  function toggleSort(key: string) {
    setParams({ sort: sort === key ? `-${key}` : sort === `-${key}` ? null : key });
  }

  return (
    <div data-fill className="flex min-h-[22rem] flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <InputGroup className="w-full sm:w-72">
          <InputGroupAddon>
            <Search />
          </InputGroupAddon>
          <InputGroupInput placeholder={searchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} />
          {q && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" aria-label="Clear search" onClick={() => setQ("")}>
                <X />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>
        {filters.map((f) => {
          const items = [{ value: ALL, label: `All ${f.label.toLowerCase()}` }, ...f.options];
          return (
            <Select
              key={f.key}
              items={items}
              value={filterValues[f.key]}
              onValueChange={(v) => setParams({ [f.key]: v === (f.defaultValue ?? ALL) ? null : String(v) })}
            >
              <SelectTrigger aria-label={f.label} className="min-w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {items.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          );
        })}
        {hasFilters && (
          <Button
            variant="ghost"
            onClick={() => {
              setQ("");
              setParams({ q: null, ...Object.fromEntries(filters.map((f) => [f.key, null])) });
            }}
          >
            Reset
          </Button>
        )}
        {toolbar && <div className="ml-auto flex items-center gap-2">{toolbar}</div>}
      </div>

      <Card className="min-h-0 flex-1 py-0 *:data-[slot=table-container]:h-full *:data-[slot=table-container]:overflow-auto">
        {isLoading ? (
          <TableSkeleton columns={columns.length} bare />
        ) : isError ? (
          <p className="p-6 text-sm text-destructive">{String((error as Error)?.message ?? error)}</p>
        ) : data && data.items.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Inbox />
              </EmptyMedia>
              <EmptyTitle>{hasFilters ? "Nothing matches" : (empty?.title ?? "Nothing here yet")}</EmptyTitle>
              <EmptyDescription>
                {hasFilters ? "Try another search or reset the filters." : empty?.description}
              </EmptyDescription>
            </EmptyHeader>
            {!hasFilters && empty?.action && <EmptyContent>{empty.action}</EmptyContent>}
          </Empty>
        ) : (
          <Table className={cn(isFetching && "opacity-60 transition-opacity")}>
            <TableHeader className="sticky top-0 z-10 bg-card shadow-[0_1px_0_var(--border)]">
              <TableRow className="hover:bg-transparent">
                {columns.map((c) => (
                  <TableHead
                    key={c.key}
                    className={cn(
                      c.align === "right" && "text-right",
                      c.hideBelow === "md" && "hidden md:table-cell",
                      c.hideBelow === "lg" && "hidden lg:table-cell",
                      c.className,
                    )}
                  >
                    {c.sort ? (
                      <button
                        className={cn("inline-flex items-center gap-1 hover:text-foreground", c.align === "right" && "flex-row-reverse")}
                        onClick={() => toggleSort(c.sort!)}
                      >
                        {c.header}
                        {sort === c.sort ? <ArrowUp className="size-3" /> : sort === `-${c.sort}` ? <ArrowDown className="size-3" /> : (
                          <ChevronsUpDown className="size-3 opacity-40" />
                        )}
                      </button>
                    ) : (
                      c.header
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((row) => {
                const href = rowHref?.(row);
                return (
                  <TableRow
                    key={rowKey(row)}
                    className={cn(href && "cursor-pointer")}
                    onClick={(e) => {
                      if (href && !(e.target as HTMLElement).closest("a,button")) router.push(href);
                    }}
                  >
                    {columns.map((c, i) => (
                      <TableCell
                        key={c.key}
                        className={cn(
                          c.align === "right" && "text-right tabular-nums",
                          c.hideBelow === "md" && "hidden md:table-cell",
                          c.hideBelow === "lg" && "hidden lg:table-cell",
                          c.className,
                        )}
                      >
                        {i === 0 && href ? (
                          <Link href={href} className="font-medium hover:underline">
                            {c.cell(row)}
                          </Link>
                        ) : (
                          c.cell(row)
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      {data && data.total > 0 && (
        <div className="flex shrink-0 items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>
            {qty((page - 1) * pageSize + 1)}–{qty(Math.min(page * pageSize, data.total))} of {qty(data.total)}
          </span>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline">
              Page {page} of {pages}
            </span>
            <Button variant="outline" size="icon-sm" aria-label="Previous page" disabled={page <= 1}
              onClick={() => setParams({ page: String(page - 1) })}>
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="icon-sm" aria-label="Next page" disabled={page >= pages}
              onClick={() => setParams({ page: String(page + 1) })}>
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TableSkeleton({ columns, bare }: { columns: number; bare?: boolean }) {
  const rows = (
    <div className="space-y-3 p-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex gap-4">
          {Array.from({ length: columns }).map((_, j) => (
            <Skeleton key={j} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
  return bare ? rows : <Card className="py-0">{rows}</Card>;
}
