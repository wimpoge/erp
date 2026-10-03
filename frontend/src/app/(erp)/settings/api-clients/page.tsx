"use client";

import { useQuery } from "@tanstack/react-query";
import { Copy, KeyRound, Plus } from "lucide-react";
import { FormEvent, useState } from "react";
import { toast } from "sonner";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { get, patch, post } from "@/lib/api";
import { dateTimeLabel } from "@/lib/format";
import { useAction } from "@/lib/hooks";

type Client = { id: number; name: string; client_id: string; active: boolean; created_at: string; last_used_at: string | null };

export default function ApiClientsPage() {
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<(Client & { client_secret: string }) | null>(null);
  const [name, setName] = useState("");
  const { data } = useQuery({ queryKey: ["api-clients"], queryFn: () => get<Client[]>("/api/settings/api-clients") });
  const create = useAction(() => post<Client & { client_secret: string }>("/api/settings/api-clients", { name }));
  const toggle = useAction(({ id, active }: { id: number; active: boolean }) => patch(`/api/settings/api-clients/${id}`, { active }),
    "Access updated.");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const c = await create.mutateAsync();
    setCreating(false);
    setName("");
    setCreated(c);
  }

  return (
    <>
      <PageHeader
        title="API clients"
        description="Outside systems (a POS, a web shop) that read products and stock and send in sales orders."
        actions={<Button onClick={() => setCreating(true)}><Plus /> New API client</Button>}
      />
      <Card className="py-0">
        {data?.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><KeyRound /></EmptyMedia>
              <EmptyTitle>No API clients yet</EmptyTitle>
              <EmptyDescription>Create one for each system that needs to talk to the ERP.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Client id</TableHead>
                <TableHead className="hidden md:table-cell">Last used</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="font-mono text-xs">{c.client_id}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{c.last_used_at ? dateTimeLabel(c.last_used_at) : "Never"}</TableCell>
                  <TableCell><StatusBadge status={c.active ? "active" : "inactive"} /></TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => toggle.mutate({ id: c.id, active: !c.active })}>
                      {c.active ? "Revoke" : "Restore"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>How a client connects</CardTitle>
          <CardDescription>Client-credentials token, then bearer requests. Full reference at <code>/docs</code> on the API.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs leading-relaxed">{`POST /api/integration/v1/token
{ "client_id": "cli_…", "client_secret": "…" }        → { "access_token": "…", "expires_in": 3600 }

GET  /api/integration/v1/products                       Authorization: Bearer <token>
GET  /api/integration/v1/warehouses/{id}/stock

POST /api/integration/v1/sales-orders
{ "external_id": "pos-KG01-000123", "customer_id": "<uuid>", "warehouse_id": "<uuid>",
  "lines": [{ "product_id": "<uuid>", "qty": 2 }] }
→ 201 created and confirmed; sending the same external_id again → 200 with the same order`}</pre>
        </CardContent>
      </Card>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <form onSubmit={submit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>New API client</DialogTitle>
              <DialogDescription>Name it after the system that will use it.</DialogDescription>
            </DialogHeader>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="c-name">Name</FieldLabel>
                <Input id="c-name" required placeholder="e.g. Store POS Bandung" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
            </FieldGroup>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
              <Button type="submit" disabled={create.isPending}>{create.isPending && <Spinner />} Create</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={created !== null} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Credentials for {created?.name}</DialogTitle>
          </DialogHeader>
          <Alert>
            <AlertTitle>Copy the secret now</AlertTitle>
            <AlertDescription>It is shown only once. Only a hash is stored; if it is lost, create a new client.</AlertDescription>
          </Alert>
          {created && (
            <div className="space-y-3 text-sm">
              <Secret label="Client id" value={created.client_id} />
              <Secret label="Client secret" value={created.client_secret} />
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>I have saved it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Secret({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded-md bg-muted px-2 py-1.5 font-mono text-xs">{value}</code>
        <Button variant="outline" size="icon-sm" aria-label={`Copy ${label}`}
          onClick={() => navigator.clipboard.writeText(value).then(() => toast.success(`${label} copied.`))}>
          <Copy />
        </Button>
      </div>
    </div>
  );
}
