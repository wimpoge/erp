"use client";

import { LogOut, Receipt, Settings, ShoppingCart, Store } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { useSession } from "@/lib/session";

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 15_000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, []);
  if (!now) return null;
  return (
    <span className="hidden text-sm tabular-nums text-slate-300 xl:inline">
      {now.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short" })} ·{" "}
      {now.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
    </span>
  );
}

const selectClass =
  "h-9 rounded-lg border-0 bg-white/10 px-2 text-sm text-white outline-none ring-1 ring-white/10 focus:ring-sky-400 [&>option]:text-slate-900";

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, locations, location, register, setLocation, setRegister, logout } = useSession();
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Sell", icon: ShoppingCart, active: pathname === "/" },
    { href: "/sales", label: "Today's sales", icon: Receipt, active: pathname.startsWith("/sales") },
    ...(user.role === "admin"
      ? [{ href: "/backoffice", label: "Back office", icon: Settings, active: pathname.startsWith("/backoffice") }]
      : []),
  ];
  const initials = user.full_name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const pickers = (
    <>
      {user.role === "admin" ? (
        <select
          aria-label="Store"
          className={`${selectClass} min-w-0 flex-1 md:max-w-56 md:flex-none`}
          value={location?.id ?? ""}
          onChange={(e) => setLocation(Number(e.target.value))}
        >
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      ) : (
        <span className="min-w-0 flex-1 truncate text-sm text-slate-200 md:flex-none">{location?.name}</span>
      )}
      {location && location.registers.length > 0 && (
        <select aria-label="Register" className={selectClass} value={register?.id ?? ""} onChange={(e) => setRegister(Number(e.target.value))}>
          {location.registers.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      )}
    </>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 bg-slate-900 text-white print:hidden">
        <div className="flex h-14 items-center gap-3 px-3 sm:px-4">
          <div className="flex items-center gap-2 pr-1">
            <Store className="h-5 w-5 text-sky-400" />
            <span className="hidden font-semibold lg:inline">Kios Gawai</span>
          </div>

          <div className="hidden items-center gap-2 md:flex">{pickers}</div>

          <nav className="flex gap-1 md:ml-2">
            {links.map(({ href, label, icon: Icon, active }) => (
              <Link
                key={href}
                href={href}
                title={label}
                className={`flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium transition ${
                  active ? "bg-white text-slate-900" : "text-slate-300 hover:bg-white/10 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="hidden md:inline">{label}</span>
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1 sm:gap-3">
            <Clock />
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-sky-500 text-xs font-semibold">
                {initials}
              </span>
              <div className="hidden leading-tight lg:block">
                <p className="text-sm">{user.full_name}</p>
                <p className="text-xs capitalize text-slate-400">{user.role}</p>
              </div>
            </div>
            <button
              onClick={logout}
              title="Log out"
              className="flex h-9 items-center gap-2 rounded-lg px-2.5 text-sm text-slate-300 hover:bg-white/10 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden lg:inline">Log out</span>
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2 border-t border-white/10 px-3 py-2 md:hidden">{pickers}</div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
