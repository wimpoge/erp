"use client";

import { useQuery } from "@tanstack/react-query";
import { MapPin, Pencil, Plus } from "lucide-react";
import { FormEvent, useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { errorMessage, get, post, put } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { money, qty } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Warehouse } from "@/lib/types";

export default function WarehousesPage() {
  const can = useCan();
  const [editing, setEditing] = useState<Warehouse | "new" | null>(null);
  const { data } = useQuery({
    queryKey: ["warehouses", "all"],
    queryFn: () => get<Warehouse[]>("/api/warehouses", { include_inactive: true }),
  });

  return (
    <>
      <PageHeader
        title="Warehouses"
        description="Distribution centers and stores that hold stock."
        actions={
          can("catalog.write") && (
            <Button onClick={() => setEditing("new")}>
              <Plus /> New warehouse
            </Button>
          )
        }
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {!data
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)
          : data.map((w) => (
              <Card key={w.id} className={w.active ? undefined : "opacity-60"}>
                <CardHeader>
                  <CardTitle>{w.name}</CardTitle>
                  <CardDescription className="flex items-center gap-1">
                    <MapPin className="size-3" /> {w.city} · <span className="font-mono">{w.code}</span>
                  </CardDescription>
                  {can("catalog.write") && (
                    <CardAction>
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${w.name}`} onClick={() => setEditing(w)}>
                        <Pencil />
                      </Button>
                    </CardAction>
                  )}
                </CardHeader>
                <CardContent className="space-y-1">
                  <p className="text-2xl font-semibold tabular-nums">{money(w.stock_value)}</p>
                  <p className="text-sm text-muted-foreground">{qty(w.units)} units in stock</p>
                  {w.address && <p className="truncate text-xs text-muted-foreground">{w.address}</p>}
                  {!w.active && <StatusBadge status="inactive" />}
                </CardContent>
              </Card>
            ))}
      </div>
      <WarehouseDialog warehouse={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function WarehouseDialog({ warehouse, onClose }: { warehouse: Warehouse | "new" | null; onClose: () => void }) {
  const existing = warehouse && warehouse !== "new" ? warehouse : null;
  const [form, setForm] = useState({ code: "", name: "", city: "", address: "", active: true });
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<typeof warehouse>(null);
  if (warehouse !== last) {
    setLast(warehouse);
    setError(null);
    setForm(existing ? { code: existing.code, name: existing.name, city: existing.city, address: existing.address ?? "", active: existing.active }
      : { code: "", name: "", city: "", address: "", active: true });
  }
  const save = useAction(() => {
    const body = { ...form, address: form.address || null };
    return existing ? put(`/api/warehouses/${existing.id}`, body) : post("/api/warehouses", body);
  }, "Warehouse saved.");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await save.mutateAsync();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <Dialog open={warehouse !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{existing ? `Edit ${existing.name}` : "New warehouse"}</DialogTitle>
          </DialogHeader>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
              <Field>
                <FieldLabel htmlFor="w-code">Code</FieldLabel>
                <Input id="w-code" required className="font-mono uppercase" value={form.code} onChange={set("code")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="w-name">Name</FieldLabel>
                <Input id="w-name" required value={form.name} onChange={set("name")} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="w-city">City</FieldLabel>
              <Input id="w-city" required value={form.city} onChange={set("city")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="w-address">Address</FieldLabel>
              <Input id="w-address" value={form.address} onChange={set("address")} />
            </Field>
            {existing && (
              <Field orientation="horizontal">
                <input id="w-active" type="checkbox" className="size-4 accent-primary" checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                <FieldLabel htmlFor="w-active">Active (only possible to switch off when empty)</FieldLabel>
              </Field>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>{save.isPending && <Spinner />} Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
