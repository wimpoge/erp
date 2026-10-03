import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { dateTimeLabel, money, qty } from "@/lib/format";
import { refHref } from "@/lib/links";
import type { StockMove } from "@/lib/types";

export const MOVE_KINDS: Record<string, string> = {
  opening: "Opening balance",
  receipt: "Goods receipt",
  delivery: "Delivery",
  transfer_in: "Transfer in",
  transfer_out: "Transfer out",
  adjustment: "Stock count",
};

// Receipts and deliveries are shown on their order's page; the ledger keeps their own number.
const refLink = (m: StockMove) =>
  m.ref_type === "goods_receipt" || m.ref_type === "delivery" ? null : refHref(m.ref_type, m.ref_id);

export function MoveQty({ value }: { value: number }) {
  return (
    <span className={`font-medium tabular-nums ${value > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}`}>
      {value > 0 ? "+" : "−"}
      {qty(Math.abs(value))}
    </span>
  );
}

export function MoveKind({ kind }: { kind: string }) {
  return <Badge variant="outline">{MOVE_KINDS[kind] ?? kind}</Badge>;
}

export function MoveRef({ move }: { move: StockMove }) {
  const href = refLink(move);
  if (!move.ref_number) return <>—</>;
  return href ? (
    <Link href={href} className="font-mono text-xs hover:underline">{move.ref_number}</Link>
  ) : (
    <span className="font-mono text-xs">{move.ref_number}</span>
  );
}

export const moveColumns = {
  at: { key: "at", header: "When", sort: "at", cell: (m: StockMove) => dateTimeLabel(m.at) },
  kind: { key: "kind", header: "Type", cell: (m: StockMove) => <MoveKind kind={m.kind} /> },
  warehouse: { key: "warehouse", header: "Warehouse", cell: (m: StockMove) => m.warehouse.code },
  ref: { key: "ref", header: "Document", cell: (m: StockMove) => <MoveRef move={m} /> },
  qty: { key: "qty", header: "Qty", sort: "qty", align: "right" as const, cell: (m: StockMove) => <MoveQty value={m.qty} /> },
  cost: { key: "cost", header: "Unit cost", align: "right" as const, hideBelow: "lg" as const, cell: (m: StockMove) => money(m.unit_cost) },
  user: { key: "user", header: "By", hideBelow: "lg" as const, cell: (m: StockMove) => m.user?.name ?? "—" },
};
