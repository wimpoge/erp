"use client";

import { FormEvent, useState } from "react";
import { PageHeader } from "@/components/erp/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { put } from "@/lib/api";
import { Company, useAction, useCompany } from "@/lib/hooks";

export default function CompanyPage() {
  const { data } = useCompany();
  return (
    <>
      <PageHeader title="Company" description="Printed on every invoice; the VAT rate applies to new orders." />
      {data ? <CompanyForm company={data} /> : <Skeleton className="h-96 max-w-3xl" />}
    </>
  );
}

function CompanyForm({ company }: { company: Company }) {
  const [form, setForm] = useState(company);
  const save = useAction(() => put("/api/settings/company", form), "Company settings saved.");
  const set = (k: keyof Company) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <form onSubmit={submit} className="grid max-w-3xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Letterhead</CardTitle>
          <CardDescription>The top of every printed invoice.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <Field className="sm:col-span-2">
              <FieldLabel htmlFor="c-name">Company name</FieldLabel>
              <Input id="c-name" required value={form.company_name} onChange={set("company_name")} />
            </Field>
            <Field className="sm:col-span-2">
              <FieldLabel htmlFor="c-address">Address</FieldLabel>
              <Input id="c-address" value={form.company_address} onChange={set("company_address")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="c-phone">Phone</FieldLabel>
              <Input id="c-phone" value={form.company_phone} onChange={set("company_phone")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="c-email">Billing email</FieldLabel>
              <Input id="c-email" type="email" value={form.company_email} onChange={set("company_email")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="c-npwp">Tax ID (NPWP)</FieldLabel>
              <Input id="c-npwp" value={form.company_tax_id} onChange={set("company_tax_id")} />
            </Field>
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Payment details</CardTitle>
          <CardDescription>Shown as &ldquo;How to pay&rdquo; on unpaid customer invoices. Leave empty to hide.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="c-bank">Bank</FieldLabel>
              <Input id="c-bank" value={form.bank_name} onChange={set("bank_name")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="c-account">Account number</FieldLabel>
              <Input id="c-account" value={form.bank_account} onChange={set("bank_account")} className="font-mono" />
            </Field>
            <Field className="sm:col-span-2">
              <FieldLabel htmlFor="c-holder">Account name</FieldLabel>
              <Input id="c-holder" value={form.bank_holder} onChange={set("bank_holder")} />
            </Field>
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tax</CardTitle>
        </CardHeader>
        <CardContent>
          <Field>
            <FieldLabel htmlFor="c-tax">VAT rate (%)</FieldLabel>
            <Input id="c-tax" type="number" min={0} max={50} className="w-28" value={form.tax_rate}
              onChange={(e) => setForm({ ...form, tax_rate: Number(e.target.value) })} />
            <FieldDescription>Existing orders and invoices keep the rate they were created with. Amounts are in {form.currency}.</FieldDescription>
          </Field>
        </CardContent>
      </Card>

      <Button type="submit" className="w-fit" disabled={save.isPending}>
        {save.isPending && <Spinner />} Save
      </Button>
    </form>
  );
}
