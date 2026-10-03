"use client";

import { useQuery } from "@tanstack/react-query";
import { MoreHorizontal, Plus } from "lucide-react";
import { FormEvent, useState } from "react";
import { PageHeader, StatusBadge } from "@/components/erp/common";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, get, patch, post } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { dateTimeLabel } from "@/lib/format";
import { useAction } from "@/lib/hooks";

type UserRow = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  active: boolean;
  locked: boolean;
  last_login_at: string | null;
};
type Role = { name: string; label: string; permissions: { key: string; label: string }[] };

export default function UsersPage() {
  const me = useMe();
  const [dialog, setDialog] = useState<{ mode: "new" } | { mode: "edit" | "password"; user: UserRow } | null>(null);
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: () => get<UserRow[]>("/api/settings/users") });
  const { data: roles } = useQuery({ queryKey: ["roles"], queryFn: () => get<Role[]>("/api/settings/roles") });
  const update = useAction(({ id, body, done }: { id: number; body: object; done: string }) =>
    patch(`/api/settings/users/${id}`, body).then(() => done), (m) => m);

  return (
    <>
      <PageHeader
        title="Users & roles"
        description="Who can log in, and what each role may do."
        actions={<Button onClick={() => setDialog({ mode: "new" })}><Plus /> Add user</Button>}
      />
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead className="hidden md:table-cell">Last login</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {users?.map((u) => (
              <TableRow key={u.id}>
                <TableCell>
                  <p className="font-medium">
                    {u.username} {u.id === me.id && <span className="text-xs font-normal text-muted-foreground">(you)</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {u.full_name} · {u.email}
                  </p>
                </TableCell>
                <TableCell><Badge variant="secondary">{u.role_label}</Badge></TableCell>
                <TableCell className="hidden text-muted-foreground md:table-cell">{u.last_login_at ? dateTimeLabel(u.last_login_at) : "Never"}</TableCell>
                <TableCell>
                  <span className="flex gap-1">
                    <StatusBadge status={u.active ? "active" : "inactive"} />
                    {u.locked && <Badge variant="destructive">Locked out</Badge>}
                  </span>
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${u.full_name}`} />}>
                      <MoreHorizontal />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setDialog({ mode: "edit", user: u })}>Change name or role</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setDialog({ mode: "password", user: u })}>Set new password</DropdownMenuItem>
                      {u.locked && (
                        <DropdownMenuItem onClick={() => update.mutate({ id: u.id, body: { unlock: true }, done: `${u.full_name} can log in again.` })}>
                          Unlock
                        </DropdownMenuItem>
                      )}
                      {u.id !== me.id && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            variant={u.active ? "destructive" : "default"}
                            onClick={() =>
                              update.mutate({
                                id: u.id,
                                body: { active: !u.active },
                                done: u.active ? `${u.full_name} can no longer log in.` : `${u.full_name} is active again.`,
                              })
                            }
                          >
                            {u.active ? "Deactivate" : "Activate"}
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">What each role can do</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {roles?.map((r) => (
            <Card key={r.name} size="sm">
              <CardHeader>
                <CardTitle>{r.label}</CardTitle>
                <CardDescription>{r.permissions.length} permissions</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {r.permissions.map((p) => <li key={p.key}>· {p.label}</li>)}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
      <UserDialog state={dialog} roles={roles ?? []} onClose={() => setDialog(null)} />
    </>
  );
}

function UserDialog({ state, roles, onClose }: {
  state: { mode: "new" } | { mode: "edit" | "password"; user: UserRow } | null;
  roles: Role[];
  onClose: () => void;
}) {
  const user = state && state.mode !== "new" ? state.user : null;
  const [form, setForm] = useState({ username: "", email: "", full_name: "", role: "sales", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<typeof state>(null);
  if (state !== last) {
    setLast(state);
    setError(null);
    setForm({ username: user?.username ?? "", email: user?.email ?? "", full_name: user?.full_name ?? "", role: user?.role ?? "sales", password: "" });
  }
  const save = useAction(() => {
    if (!state || state.mode === "new") return post("/api/settings/users", form);
    if (state.mode === "password") return patch(`/api/settings/users/${state.user.id}`, { password: form.password });
    return patch(`/api/settings/users/${state.user.id}`, { full_name: form.full_name, role: form.role });
  }, "User saved.");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await save.mutateAsync();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const roleItems = roles.map((r) => ({ value: r.name, label: r.label }));
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <Dialog open={state !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{state?.mode === "new" ? "Add user" : state?.mode === "password" ? `New password for ${user?.username}` : `Edit ${user?.username}`}</DialogTitle>
            {state?.mode === "password" && <DialogDescription>Their other sessions stay logged in until they expire.</DialogDescription>}
          </DialogHeader>
          <FieldGroup>
            {state?.mode !== "password" && (
              <>
                <Field>
                  <FieldLabel htmlFor="u-name">Full name</FieldLabel>
                  <Input id="u-name" required value={form.full_name} onChange={set("full_name")} />
                </Field>
                {state?.mode === "new" && (
                  <Field>
                    <FieldLabel htmlFor="u-username">Username</FieldLabel>
                    <Input id="u-username" required minLength={3} pattern="[a-zA-Z0-9._-]+" autoCapitalize="none" value={form.username}
                      onChange={set("username")} />
                    <FieldDescription>Used to log in. Letters, numbers, dots, dashes.</FieldDescription>
                  </Field>
                )}
                {state?.mode === "new" && (
                  <Field>
                    <FieldLabel htmlFor="u-email">Email</FieldLabel>
                    <Input id="u-email" type="email" required value={form.email} onChange={set("email")} />
                  </Field>
                )}
                <Field>
                  <FieldLabel>Role</FieldLabel>
                  <Select items={roleItems} value={form.role} onValueChange={(v) => setForm({ ...form, role: String(v) })}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {roleItems.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Field>
              </>
            )}
            {state?.mode !== "edit" && (
              <Field>
                <FieldLabel htmlFor="u-password">Password</FieldLabel>
                <Input id="u-password" type="password" minLength={8} required autoComplete="new-password" value={form.password}
                  onChange={set("password")} />
                <FieldDescription>At least 8 characters. Share it in person, not by email.</FieldDescription>
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
