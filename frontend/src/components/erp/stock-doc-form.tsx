"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { errorMessage, post } from "@/lib/api";
import { todayIso } from "@/lib/format";
import { useWarehouses } from "@/lib/hooks";
import { Line, LinesEditor, newLine, validLines } from "./lines-editor";

function WarehouseSelect({ value, onChange, label, invalid, exclude }: {
  value: string; onChange: (v: string) => void; label: string; invalid?: boolean; exclude?: string;
}) {
  const { data } = useWarehouses();
  const items = (data ?? []).filter((w) => String(w.id) !== exclude).map((w) => ({ value: String(w.id), label: w.name }));
  return (
    <Field data-invalid={invalid}>
      <FieldLabel>{label}</FieldLabel>
      <Select items={items} value={value || null} onValueChange={(v) => onChange(String(v ?? ""))}>
        <SelectTrigger className="w-full" aria-invalid={invalid || undefined}>
          <SelectValue placeholder="Choose a warehouse" />
        </SelectTrigger>
        <SelectContent>
          {items.map((w) => <SelectItem key={w.value} value={w.value}>{w.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
  );
}

/** New transfer (two warehouses + quantities) or new stock count (one warehouse + counted quantities). */
export function StockDocForm({ kind }: { kind: "transfer" | "count" }) {
  const router = useRouter();
  const transfer = kind === "transfer";
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState(todayIso());
  const [text, setText] = useState("");
  const [lines, setLines] = useState<Line[]>([newLine()]);
  const [showErrors, setShowErrors] = useState(false);
  const [busy, setBusy] = useState<null | "draft" | "validate">(null);
  const [error, setError] = useState<string | null>(null);
  const mode = transfer ? "quantity" : "count";

  async function save(validate: boolean) {
    setShowErrors(true);
    setError(null);
    if (!from || (transfer && !to) || (!transfer && !text.trim()) || !validLines(lines, mode)) {
      setError("Fill in the highlighted fields.");
      return;
    }
    setBusy(validate ? "validate" : "draft");
    try {
      const doc = transfer
        ? await post<{ id: number; number: string }>("/api/transfers", {
            from_warehouse_id: Number(from), to_warehouse_id: Number(to), transfer_date: date, note: text || null,
            lines: lines.map((l) => ({ product_id: l.product!.id, qty: l.qty })),
          })
        : await post<{ id: number; number: string }>("/api/adjustments", {
            warehouse_id: Number(from), adjustment_date: date, reason: text.trim(),
            lines: lines.map((l) => ({ product_id: l.product!.id, counted_qty: l.qty })),
          });
      const base = transfer ? "/api/transfers" : "/api/adjustments";
      if (validate) await post(`${base}/${doc.id}/validate`);
      toast.success(`${doc.number} ${validate ? "done; stock updated" : "saved as draft"}.`);
      router.push(`${transfer ? "/inventory/transfers" : "/inventory/adjustments"}/${doc.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <Card>
          <CardContent>
            <FieldGroup className="grid gap-4 md:grid-cols-2">
              <WarehouseSelect label={transfer ? "From" : "Warehouse"} value={from} onChange={setFrom} invalid={showErrors && !from} />
              {transfer && (
                <WarehouseSelect label="To" value={to} onChange={setTo} invalid={showErrors && !to} exclude={from} />
              )}
              <Field>
                <FieldLabel htmlFor="doc-date">Date</FieldLabel>
                <Input id="doc-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </Field>
              <Field data-invalid={showErrors && !transfer && !text.trim()}>
                <FieldLabel htmlFor="doc-text">{transfer ? "Note" : "Reason"}</FieldLabel>
                <Input id="doc-text" value={text} placeholder={transfer ? "Optional" : "e.g. Monthly count, damaged in storage"}
                  aria-invalid={showErrors && !transfer && !text.trim() ? true : undefined} onChange={(e) => setText(e.target.value)} />
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{transfer ? "Products to move" : "Counted quantities"}</CardTitle>
          </CardHeader>
          <CardContent>
            <LinesEditor mode={mode} lines={lines} onChange={setLines} warehouseId={from ? Number(from) : undefined} showErrors={showErrors} />
          </CardContent>
        </Card>
      </div>
      <Card className="xl:sticky xl:top-20 xl:self-start">
        <CardContent className="space-y-3">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Button className="w-full" disabled={busy !== null} onClick={() => save(true)}>
            {busy === "validate" && <Spinner />} {transfer ? "Move stock now" : "Apply count now"}
          </Button>
          <Button className="w-full" variant="outline" disabled={busy !== null} onClick={() => save(false)}>
            {busy === "draft" && <Spinner />} Save as draft
          </Button>
          <FieldDescription>
            {transfer
              ? "Moving stock takes it out of the first warehouse and into the second at average cost."
              : "Counted quantities replace what the system thinks is there; the difference is booked as an adjustment."}
          </FieldDescription>
        </CardContent>
      </Card>
    </div>
  );
}
