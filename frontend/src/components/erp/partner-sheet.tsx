"use client";

import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { errorMessage, get, post, put } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { Customer, CustomerGroup, Supplier } from "@/lib/types";

type Kind = "customer" | "supplier";
type Partner = Customer | Supplier;

const empty = { name: "", email: "", phone: "", address: "", city: "", group_id: "", credit_limit: 0, payment_terms_days: 30, active: true };

/** Create or edit a customer or supplier in a side panel. */
export function PartnerSheet({
  kind,
  open,
  onOpenChange,
  partner,
  onSaved,
}: {
  kind: Kind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  partner?: Partner | null;
  onSaved?: (p: Partner) => void;
}) {
  const customer = kind === "customer";
  const { data: groups } = useQuery({
    queryKey: ["customer-groups"],
    queryFn: () => get<CustomerGroup[]>("/api/customer-groups"),
    enabled: customer && open,
  });
  const [form, setForm] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<{ open: boolean; id?: number }>({ open: false });
  if (open !== last.open || partner?.id !== last.id) {
    setLast({ open, id: partner?.id });
    if (open) {
      setError(null);
      setForm(
        partner
          ? {
              name: partner.name,
              email: partner.email ?? "",
              phone: partner.phone ?? "",
              address: partner.address ?? "",
              city: partner.city ?? "",
              group_id: "group" in partner && partner.group ? String(partner.group.id) : "",
              credit_limit: "credit_limit" in partner ? partner.credit_limit : 0,
              payment_terms_days: partner.payment_terms_days,
              active: partner.active,
            }
          : { ...empty, payment_terms_days: customer ? 7 : 30 },
      );
    }
  }

  const save = useAction(async () => {
    const base = customer ? "/api/customers" : "/api/suppliers";
    const body = {
      name: form.name.trim(),
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      city: form.city.trim() || null,
      payment_terms_days: form.payment_terms_days,
      active: form.active,
      ...(customer ? { group_id: form.group_id ? Number(form.group_id) : null, credit_limit: form.credit_limit } : {}),
    };
    return partner ? put<Partner>(`${base}/${partner.id}`, body) : post<Partner>(base, body);
  }, (p) => `${p.name} saved.`);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const p = await save.mutateAsync();
      onOpenChange(false);
      onSaved?.(p);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const groupItems = [{ value: "", label: "No group" }, ...(groups ?? []).map((g) => ({ value: String(g.id), label: `${g.name} (−${g.discount_pct}%)` }))];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} className="flex h-full flex-col">
          <SheetHeader>
            <SheetTitle>{partner ? `Edit ${partner.name}` : customer ? "New customer" : "New supplier"}</SheetTitle>
            <SheetDescription>{partner ? `Code ${partner.code}` : "A code is assigned automatically."}</SheetDescription>
          </SheetHeader>
          <FieldGroup className="flex-1 px-4">
            <Field>
              <FieldLabel htmlFor="p-name">Name</FieldLabel>
              <Input id="p-name" required autoFocus value={form.name} onChange={set("name")} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="p-email">Email</FieldLabel>
                <Input id="p-email" type="email" value={form.email} onChange={set("email")} />
              </Field>
              <Field>
                <FieldLabel htmlFor="p-phone">Phone</FieldLabel>
                <Input id="p-phone" value={form.phone} onChange={set("phone")} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="p-address">Address</FieldLabel>
              <Input id="p-address" value={form.address} onChange={set("address")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="p-city">City</FieldLabel>
              <Input id="p-city" value={form.city} onChange={set("city")} />
            </Field>
            {customer && (
              <Field>
                <FieldLabel>Customer group</FieldLabel>
                <Select items={groupItems} value={form.group_id} onValueChange={(v) => setForm({ ...form, group_id: String(v ?? "") })}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {groupItems.map((g) => (
                      <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>The group&apos;s discount is applied to new sales orders.</FieldDescription>
              </Field>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="p-terms">Payment terms (days)</FieldLabel>
                <Input id="p-terms" type="number" min={0} max={365} value={form.payment_terms_days}
                  onChange={(e) => setForm({ ...form, payment_terms_days: Number(e.target.value) })} />
              </Field>
              {customer && (
                <Field>
                  <FieldLabel htmlFor="p-credit">Credit limit (Rp)</FieldLabel>
                  <Input id="p-credit" type="number" min={0} step={1_000_000} value={form.credit_limit}
                    onChange={(e) => setForm({ ...form, credit_limit: Number(e.target.value) })} />
                </Field>
              )}
            </div>
            {customer && <FieldDescription className="-mt-2">Credit limit 0 means no limit.</FieldDescription>}
            {partner && (
              <Field orientation="horizontal">
                <input id="p-active" type="checkbox" className="size-4 accent-primary" checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                <FieldLabel htmlFor="p-active">Active (can be used on new orders)</FieldLabel>
              </Field>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </FieldGroup>
          <SheetFooter>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <Spinner />} Save
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
