"use client";

import { Search, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Dialog, inputClass } from "@/components/ui";
import { api, Customer } from "@/lib/api";

export function CustomerPicker({
  open,
  onClose,
  onPick,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (c: Customer) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);

  const term = q.trim();
  const searching = term.length >= 2;

  useEffect(() => {
    if (!open || !searching) return;
    const timer = setTimeout(() => {
      setLoading(true);
      api<Customer[]>(`/api/customers?q=${encodeURIComponent(term)}&limit=10`)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [term, open, searching]);

  function close() {
    setQ("");
    setResults([]);
    onClose();
  }

  const shown = searching ? results : [];

  return (
    <Dialog open={open} onClose={close} title="Find customer">
      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            autoFocus
            className={`${inputClass} pl-10`}
            placeholder="Name, phone number or member code"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && shown[0]) {
                onPick(shown[0]);
                close();
              }
            }}
          />
        </div>
        <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
          {shown.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => {
                  onPick(c);
                  close();
                }}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-slate-50"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                  <UserRound className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{c.name}</span>
                  <span className="block truncate text-xs text-slate-500">
                    {c.phone} · {c.code}
                  </span>
                </span>
                {c.discount_rate > 0 ? <Badge tone="green">{c.group} −{c.discount_rate}%</Badge> : <Badge>{c.group}</Badge>}
              </button>
            </li>
          ))}
        </ul>
        <p className="text-center text-sm text-slate-500">
          {!searching
            ? "Type at least 2 characters."
            : loading && shown.length === 0
              ? "Searching…"
              : shown.length === 0
                ? "No customer found."
                : null}
        </p>
      </div>
    </Dialog>
  );
}
