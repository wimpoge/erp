"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSeparator } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, errorMessage } from "@/lib/api";

const DEMO = [
  { email: "admin@example.com", role: "Administrator", note: "everything, incl. users" },
  { email: "manager@example.com", role: "Manager", note: "all modules" },
  { email: "sales@example.com", role: "Sales", note: "customers & sales orders" },
  { email: "purchasing@example.com", role: "Purchasing", note: "suppliers & purchase orders" },
  { email: "warehouse@example.com", role: "Warehouse", note: "receive, ship, transfer, count" },
  { email: "finance@example.com", role: "Accountant", note: "invoices, bills, payments" },
];
const DEMO_PASSWORD = "demo1234";

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function login(creds: { email: string; password: string }) {
    setBusy(creds.email);
    setError(null);
    try {
      await api("/api/auth/login", { method: "POST", json: creds });
      queryClient.removeQueries();
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (e) {
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    login({ email, password });
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted p-4 md:p-10">
      <div className="flex w-full max-w-md flex-col gap-6">
        <div className="flex items-center gap-2 self-center font-semibold">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary text-sm text-primary-foreground">N</div>
          Nusantara ERP
        </div>
        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Welcome back</CardTitle>
            <CardDescription>Log in with your work email</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit}>
              <FieldGroup>
                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
                <Field>
                  <FieldLabel htmlFor="email">Email</FieldLabel>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    placeholder="you@company.com"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
                <Field>
                  <Button type="submit" disabled={busy !== null}>
                    {busy === email && <Spinner />} Log in
                  </Button>
                </Field>
                <FieldSeparator>Or try a demo role</FieldSeparator>
                <div className="grid gap-2">
                  {DEMO.map((d) => (
                    <Button
                      key={d.email}
                      type="button"
                      variant="outline"
                      className="h-auto justify-between py-2"
                      disabled={busy !== null}
                      onClick={() => login({ email: d.email, password: DEMO_PASSWORD })}
                    >
                      <span className="flex items-center gap-2">
                        {busy === d.email && <Spinner />}
                        <Badge variant="secondary">{d.role}</Badge>
                      </span>
                      <span className="truncate text-xs font-normal text-muted-foreground">{d.note}</span>
                    </Button>
                  ))}
                </div>
                <FieldDescription className="text-center">
                  Demo accounts use the password <code>{DEMO_PASSWORD}</code>. Data resets from time to time.
                </FieldDescription>
              </FieldGroup>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
