"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { qty as fmtQty, todayIso } from "@/lib/format";
import type { ProductRef } from "@/lib/types";

export type FulfilLine = {
  id: number;
  product: ProductRef;
  remaining: number;
  /** Most that can go now (e.g. stock on hand for deliveries). */
  max: number;
  note?: string;
};

/** Deliver (sales) or receive (purchasing) some or all of what is still open on an order. */
export function FulfilDialog({
  open,
  onOpenChange,
  title,
  description,
  dateLabel,
  confirmLabel,
  lines,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  dateLabel: string;
  confirmLabel: string;
  lines: FulfilLine[];
  onSubmit: (qtyByLine: Record<number, number>, date: string) => Promise<unknown>;
}) {
  const [qty, setQty] = useState<Record<number, number>>({});
  const [date, setDate] = useState(todayIso());
  const [busy, setBusy] = useState(false);

  // Fresh suggestions every time the dialog opens: as much as can go now.
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setQty(Object.fromEntries(lines.map((l) => [l.id, Math.min(l.remaining, Math.max(0, l.max))])));
      setDate(todayIso());
    }
  }

  const units = Object.values(qty).reduce((a, b) => a + (b || 0), 0);

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[50vh] overflow-y-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead className="text-right">Still open</TableHead>
                <TableHead className="w-32 text-right">Now</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>
                    <p className="font-medium">{l.product.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {l.product.sku}
                      {l.note && <span className={l.max < l.remaining ? " text-destructive" : ""}> · {l.note}</span>}
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtQty(l.remaining)}</TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={0}
                      max={l.remaining}
                      className="text-right tabular-nums"
                      value={qty[l.id] ?? 0}
                      onChange={(e) =>
                        setQty({ ...qty, [l.id]: Math.min(l.remaining, Math.max(0, Math.floor(Number(e.target.value)))) })
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <Field orientation="horizontal" className="max-w-sm">
          <FieldLabel htmlFor="fulfil-date" className="shrink-0 whitespace-nowrap">
            {dateLabel}
          </FieldLabel>
          <Input id="fulfil-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button
            disabled={busy || units === 0}
            onClick={async () => {
              setBusy(true);
              try {
                await onSubmit(qty, date);
                onOpenChange(false);
              } catch {
                // reason already shown as a toast
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy && <Spinner />} {confirmLabel} ({fmtQty(units)} unit{units === 1 ? "" : "s"})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
