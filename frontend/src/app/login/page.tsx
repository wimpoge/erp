"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Boxes, Eye, EyeOff, Lock, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { LoginArt } from "@/components/login-art";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel, FieldSeparator } from "@/components/ui/field";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { api, errorMessage } from "@/lib/api";

const DEMO = [
  { username: "admin", role: "Administrator" },
  { username: "manager", role: "Manager" },
  { username: "sales", role: "Sales" },
  { username: "purchasing", role: "Purchasing" },
  { username: "warehouse", role: "Warehouse" },
  { username: "finance", role: "Accountant" },
];
const DEMO_PASSWORD = "demo1234";

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function login(creds: { username: string; password: string }) {
    setBusy(creds.username);
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
    login({ username, password });
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden bg-muted p-4 md:p-10">
      {/* soft colour behind the card */}
      <div aria-hidden className="pointer-events-none absolute -top-40 -left-40 size-128 rounded-full bg-violet-500/20 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -right-40 -bottom-40 size-128 rounded-full bg-indigo-500/20 blur-3xl" />

      <div className="relative grid w-full max-w-5xl overflow-hidden rounded-3xl border bg-card shadow-2xl md:grid-cols-2">
        <div className="flex flex-col justify-center gap-8 p-8 sm:p-12">
          <div className="flex items-center gap-2 font-semibold">
            <span className="flex size-9 items-center justify-center rounded-xl bg-violet-600 text-white">
              <Boxes className="size-5" />
            </span>
            ERP
          </div>
          <div className="space-y-1.5">
            <h1 className="text-3xl font-semibold tracking-tight">Welcome back 👋</h1>
            <p className="text-muted-foreground">Log in with your username to run the business.</p>
          </div>

          <form onSubmit={submit}>
            <FieldGroup>
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor="username">Username</FieldLabel>
                <InputGroup className="h-11 rounded-xl">
                  <InputGroupAddon>
                    <UserRound />
                  </InputGroupAddon>
                  <InputGroupInput
                    id="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    autoComplete="username"
                    placeholder="e.g. admin"
                    required
                    autoFocus
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </InputGroup>
              </Field>
              <Field>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <InputGroup className="h-11 rounded-xl">
                  <InputGroupAddon>
                    <Lock />
                  </InputGroupAddon>
                  <InputGroupInput
                    id="password"
                    type={shown ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      size="icon-xs"
                      aria-label={shown ? "Hide password" : "Show password"}
                      onClick={() => setShown(!shown)}
                    >
                      {shown ? <EyeOff /> : <Eye />}
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
              </Field>
              <Button
                type="submit"
                size="lg"
                className="h-11 rounded-xl bg-violet-600 text-white hover:bg-violet-700"
                disabled={busy !== null}
              >
                {busy === username && <Spinner />} Log in {busy !== username && <ArrowRight />}
              </Button>
              <FieldSeparator className="[&_[data-slot=field-separator-content]]:bg-card">Or try a demo role</FieldSeparator>
              <div className="grid grid-cols-2 gap-2">
                {DEMO.map((d) => (
                  <Button
                    key={d.username}
                    type="button"
                    variant="outline"
                    className="h-10 justify-start rounded-xl"
                    disabled={busy !== null}
                    onClick={() => login({ username: d.username, password: DEMO_PASSWORD })}
                    title={`Log in as ${d.username}`}
                  >
                    {busy === d.username && <Spinner />}
                    {d.role}
                  </Button>
                ))}
              </div>
              <p className="text-center text-xs text-muted-foreground">
                Demo accounts use the password <code>{DEMO_PASSWORD}</code>. Data resets from time to time.
              </p>
            </FieldGroup>
          </form>
        </div>

        <div className="relative hidden min-h-152 md:block">
          <LoginArt variant="erp" />
          <div className="absolute inset-x-0 top-0 p-10 text-white">
            <p className="text-sm font-medium tracking-wide text-white/80 uppercase">Enterprise resource planning</p>
            <p className="mt-2 max-w-xs text-2xl leading-snug font-semibold">
              Stock, sales, purchasing and money, in one place.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
