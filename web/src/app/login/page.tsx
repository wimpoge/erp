"use client";

import { Eye, EyeOff, Store } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button, Field, inputClass } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { username: "kasir1", password: "kasir123", label: "Cashier · Jakarta Selatan" },
  { username: "admin", password: "admin123", label: "Admin · all stores" },
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e?: FormEvent, account?: { username: string; password: string }) {
    e?.preventDefault();
    const creds = account ?? { username, password };
    if (!creds.username || !creds.password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/login", { method: "POST", json: creds });
      const next = new URLSearchParams(window.location.search).get("next");
      // Only same-site paths, never an absolute URL from the query string.
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 to-slate-700 p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center text-white">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-white/10">
            <Store className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-semibold">Kios Gawai POS</h1>
          <p className="text-sm text-slate-300">Log in to start selling</p>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-2xl bg-white p-6 shadow-xl">
          <Field label="Username">
            <input
              className={inputClass}
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field label="Password">
            <div className="relative">
              <input
                className={`${inputClass} pr-11`}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-slate-400 hover:text-slate-700"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </Field>
          {error && (
            <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" className="w-full" loading={busy}>
            Log in
          </Button>
        </form>

        <div className="rounded-2xl bg-white/10 p-4 text-sm text-slate-200">
          <p className="mb-2 font-medium text-white">Demo accounts</p>
          <div className="space-y-1.5">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.username}
                disabled={busy}
                onClick={() => {
                  setUsername(a.username);
                  setPassword(a.password);
                  submit(undefined, a);
                }}
                className="flex w-full items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-left hover:bg-white/15"
              >
                <span>
                  <span className="font-mono text-white">{a.username}</span> / <span className="font-mono">{a.password}</span>
                </span>
                <span className="text-xs text-slate-300">{a.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
