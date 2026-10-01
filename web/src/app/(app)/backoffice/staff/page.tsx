"use client";

import { KeyRound, Lock, UserPlus } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/toast";
import { Badge, Button, Dialog, Field, Spinner, inputClass } from "@/components/ui";
import { api, dateTime, errorMessage, User } from "@/lib/api";
import { useSession } from "@/lib/session";

type Editing = { mode: "new" } | { mode: "edit"; user: User } | { mode: "password"; user: User };

export default function StaffPage() {
  const { user: me, locations } = useSession();
  const toast = useToast();
  const [users, setUsers] = useState<User[] | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);

  const load = useCallback(() => {
    api<User[]>("/api/users")
      .then(setUsers)
      .catch((e) => toast(errorMessage(e), "error"));
  }, [toast]);

  useEffect(load, [load]);

  async function update(user: User, changes: Record<string, unknown>, done: string) {
    try {
      await api(`/api/users/${user.id}`, { method: "PATCH", json: changes });
      toast(done, "success");
      load();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <p className="mr-auto text-sm text-slate-600">Cashiers sell in one store. Admins can work in every store and use the back office.</p>
        <Button onClick={() => setEditing({ mode: "new" })}>
          <UserPlus className="h-4 w-4" /> Add staff
        </Button>
      </div>

      <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        {users === null ? (
          <Spinner />
        ) : (
          <ul className="divide-y divide-slate-100">
            {users.map((u) => (
              <li key={u.id} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${u.active ? "" : "opacity-50"}`}>
                <div className="min-w-48 flex-1">
                  <p className="font-medium">
                    {u.full_name} {u.id === me.id && <span className="text-xs font-normal text-slate-500">(you)</span>}
                  </p>
                  <p className="text-sm text-slate-500">
                    @{u.username} · {u.location?.name ?? "All stores"}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={u.role === "admin" ? "blue" : "slate"}>{u.role}</Badge>
                  {!u.active && <Badge tone="red">deactivated</Badge>}
                  {u.locked && <Badge tone="amber">locked out</Badge>}
                </div>
                <p className="hidden w-40 text-xs text-slate-500 md:block">
                  {u.last_login_at ? `Last login ${dateTime(u.last_login_at)}` : "Never logged in"}
                </p>
                <div className="flex gap-1">
                  {u.locked && (
                    <Button size="sm" variant="ghost" onClick={() => update(u, { unlock: true }, `${u.full_name} can log in again.`)}>
                      <Lock className="h-4 w-4" /> Unlock
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => setEditing({ mode: "password", user: u })}>
                    <KeyRound className="h-4 w-4" /> Password
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing({ mode: "edit", user: u })}>
                    Edit
                  </Button>
                  {u.id !== me.id && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        update(u, { active: !u.active }, u.active ? `${u.full_name} can no longer log in.` : `${u.full_name} is active again.`)
                      }
                    >
                      {u.active ? "Deactivate" : "Activate"}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <StaffDialog
        editing={editing}
        locations={locations}
        onClose={() => setEditing(null)}
        onSaved={(message) => {
          setEditing(null);
          toast(message, "success");
          load();
        }}
      />
    </div>
  );
}

function StaffDialog({
  editing,
  locations,
  onClose,
  onSaved,
}: {
  editing: Editing | null;
  locations: { id: number; name: string }[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const existing = editing && editing.mode !== "new" ? editing.user : null;
  const [form, setForm] = useState({ username: "", full_name: "", password: "", role: "cashier", location_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastEditing, setLastEditing] = useState<Editing | null>(null);

  // Reset the form whenever a different person (or "new") is opened.
  if (editing !== lastEditing) {
    setLastEditing(editing);
    setError(null);
    setForm({
      username: existing?.username ?? "",
      full_name: existing?.full_name ?? "",
      password: "",
      role: existing?.role ?? "cashier",
      location_id: String(existing?.location?.id ?? locations[0]?.id ?? ""),
    });
  }

  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(null);
    const location_id = form.role === "admin" && !form.location_id ? null : Number(form.location_id) || null;
    try {
      if (editing.mode === "new") {
        await api("/api/users", { method: "POST", json: { ...form, location_id } });
        onSaved(`${form.full_name} can now log in as ${form.username.toLowerCase()}.`);
      } else if (editing.mode === "password") {
        await api(`/api/users/${editing.user.id}`, { method: "PATCH", json: { password: form.password } });
        onSaved(`New password set for ${editing.user.full_name}.`);
      } else {
        await api(`/api/users/${editing.user.id}`, {
          method: "PATCH",
          json: { full_name: form.full_name, role: form.role, location_id },
        });
        onSaved(`${form.full_name} updated.`);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const title =
    editing?.mode === "new" ? "Add staff" : editing?.mode === "password" ? `New password for ${existing?.full_name}` : `Edit ${existing?.full_name}`;

  return (
    <Dialog open={editing !== null} onClose={onClose} title={title}>
      <form onSubmit={submit} className="space-y-4">
        {editing?.mode !== "password" && (
          <>
            <Field label="Full name">
              <input className={inputClass} value={form.full_name} onChange={set("full_name")} required autoFocus />
            </Field>
            {editing?.mode === "new" && (
              <Field label="Username" hint="Letters, numbers, dots or dashes. Used to log in.">
                <input className={inputClass} value={form.username} onChange={set("username")} required autoCapitalize="none" />
              </Field>
            )}
            <Field label="Role">
              <select className={inputClass} value={form.role} onChange={set("role")}>
                <option value="cashier">Cashier: sells in one store</option>
                <option value="admin">Admin: all stores and back office</option>
              </select>
            </Field>
            <Field label="Store">
              <select className={inputClass} value={form.location_id} onChange={set("location_id")}>
                {form.role === "admin" && <option value="">All stores</option>}
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
        {editing?.mode !== "edit" && (
          <Field label={editing?.mode === "new" ? "Password" : "New password"} hint="At least 6 characters. Share it with them in person.">
            <input className={inputClass} type="text" value={form.password} onChange={set("password")} required minLength={6} autoComplete="new-password" />
          </Field>
        )}
        {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
